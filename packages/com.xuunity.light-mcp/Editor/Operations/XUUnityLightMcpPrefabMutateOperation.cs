using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using UnityEditor;
using UnityEngine;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;

namespace XUUnity.LightMcp.Editor.Operations
{
    internal sealed class XUUnityLightMcpPrefabMutateOperation : IXUUnityLightMcpOperation
    {
        public const string RegisteredOperationName = "unity.prefab.mutate";

        public string OperationName => RegisteredOperationName;

        public XUUnityLightMcpResponse Execute(XUUnityLightMcpRequest request)
        {
            var args = string.IsNullOrWhiteSpace(request.args_json)
                ? new XUUnityLightMcpPrefabMutationArgs()
                : JsonUtility.FromJson<XUUnityLightMcpPrefabMutationArgs>(request.args_json)
                  ?? new XUUnityLightMcpPrefabMutationArgs();

            var payload = new XUUnityLightMcpPrefabMutationPayload
            {
                project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                generated_at_utc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                prefab_path = args.prefabPath ?? "",
                preview_only = args.previewOnly || !args.approve,
                requested_operation_count = (args.operations ?? Array.Empty<XUUnityLightMcpPrefabMutationOperation>()).Length
            };

            if (!XUUnityLightMcpPrefabMutator.TryValidateArgs(args, out var argsError))
            {
                payload.errors.Add(argsError);
                payload.recommended_next_action = "fix_the_transaction_shape_then_preview_again";
                return Respond(request, payload);
            }

            var loaded = XUUnityLightMcpPrefabInspector.Load(args.prefabPath);
            if (loaded.Error != null)
            {
                payload.errors.Add(loaded.Error);
                payload.recommended_next_action = "supply_an_existing_project_relative_prefab_path";
                return Respond(request, payload);
            }

            payload.prefab_path = loaded.NormalizedPath;
            payload.prefab_guid = loaded.Guid;
            payload.sha256_before = FileSha256(loaded.NormalizedPath);

            var expected = (args.expectedSha256 ?? "").Trim();
            if (!string.IsNullOrEmpty(expected)
                && !string.Equals(expected, payload.sha256_before, StringComparison.OrdinalIgnoreCase))
            {
                payload.drift_guard = "drifted";
                payload.errors.Add(XUUnityLightMcpUiTreeBuilder.Diagnostic(
                    "prefab_mutation_asset_drifted",
                    "The prefab file no longer matches the hash this transaction was built against, so the editor's "
                    + "loaded copy may be stale and applying it could overwrite an out-of-band edit.",
                    $"expected {expected}, observed {payload.sha256_before}"));
                payload.recommended_next_action = "run_unity_project_refresh_then_rebuild_the_transaction";
                return Respond(request, payload);
            }

            // A write goes through the editor's in-memory copy. Whether that copy still matches the file
            // is only decidable from the caller's own expectedSha256: from inside the editor, a file
            // rewritten by an external tool and a file Unity itself reimported look identical, so an
            // inferred drift check would refuse legitimate writes. Naming the unguarded case is the
            // honest alternative to guessing.
            payload.drift_guard = string.IsNullOrEmpty(expected) ? "unguarded" : "precondition_matched";
            if (payload.drift_guard == "unguarded")
            {
                payload.warnings.Add(XUUnityLightMcpUiTreeBuilder.Diagnostic(
                    "prefab_mutation_unguarded_by_precondition",
                    "No expectedSha256 was supplied, so this write cannot detect that the file changed on disk "
                    + "since it was inspected. Pass the observed hash as expectedSha256, and always run "
                    + "unity_project_refresh between a raw file edit and the next transaction.",
                    payload.sha256_before));
            }

            RunTransaction(args, loaded, payload);
            return Respond(request, payload);
        }

        static void RunTransaction(
            XUUnityLightMcpPrefabMutationArgs args,
            XUUnityLightMcpPrefabLoadResult loaded,
            XUUnityLightMcpPrefabMutationPayload payload)
        {
            var allowed = XUUnityLightMcpPrefabMutator.ResolveAllowedComponentTypes(args.allowedComponentTypes);
            GameObject contents = null;
            try
            {
                contents = PrefabUtility.LoadPrefabContents(loaded.NormalizedPath);
                var failure = ApplyOperations(args, contents, allowed, payload);
                payload.planned_change_count = CountStatus(payload.changes, "applied");
                payload.no_op_count = CountStatus(payload.changes, "no_op");

                if (failure != null)
                {
                    payload.status = "rolled_back";
                    payload.rolled_back = true;
                    payload.rollback_reason = failure;
                    payload.applied = false;
                    payload.success = false;
                    payload.errors.Add(XUUnityLightMcpUiTreeBuilder.Diagnostic(
                        "prefab_mutation_rolled_back",
                        "An operation failed, so the whole transaction was discarded and the prefab asset is untouched.",
                        failure));
                    payload.recommended_next_action = "fix_the_failing_operation_then_preview_again";
                    return;
                }

                payload.post_validation = ValidateContents(contents, payload);
                if (!payload.post_validation.passed)
                {
                    payload.status = "rolled_back";
                    payload.rolled_back = true;
                    payload.rollback_reason = "post_mutation_validation_failed";
                    payload.applied = false;
                    payload.success = false;
                    payload.errors.Add(XUUnityLightMcpUiTreeBuilder.Diagnostic(
                        "prefab_mutation_validation_failed",
                        "The mutated prefab failed binding validation, so it was discarded instead of saved.",
                        string.Join(", ", payload.post_validation.defect_types)));
                    payload.recommended_next_action = "inspect_post_validation_defects_before_retrying";
                    return;
                }

                payload.reversible_patch_json = BuildReversiblePatch(payload);
                if (payload.no_op_count > 0)
                {
                    payload.warnings.Add(XUUnityLightMcpUiTreeBuilder.Diagnostic(
                        "prefab_mutation_no_op_operations",
                        "Some operations left the serialized value unchanged and are reported as no_op, not applied.",
                        $"{payload.no_op_count} of {payload.changes.Count}"));
                }

                if (payload.preview_only)
                {
                    payload.status = "previewed";
                    payload.applied = false;
                    payload.success = true;
                    payload.proof_class = XUUnityLightMcpUiRead.ProofSemanticTree;
                    payload.sha256_after = payload.sha256_before;
                    payload.recommended_next_action = "review_the_delta_then_re_run_with_approve_true_and_preview_only_false";
                    return;
                }

                PrefabUtility.SaveAsPrefabAsset(contents, loaded.NormalizedPath);
                AssetDatabase.ImportAsset(loaded.NormalizedPath, ImportAssetOptions.ForceUpdate);
                payload.sha256_after = FileSha256(loaded.NormalizedPath);
                payload.applied = true;
                payload.status = "applied";
                payload.success = true;
                payload.proof_class = XUUnityLightMcpUiRead.ProofSemanticTree;
                payload.recommended_next_action = "re_render_or_re_compare_the_reference_to_confirm_the_intended_visual_change";
            }
            catch (Exception exception)
            {
                payload.status = "rolled_back";
                payload.rolled_back = true;
                payload.rollback_reason = exception.Message;
                payload.applied = false;
                payload.success = false;
                payload.errors.Add(XUUnityLightMcpUiTreeBuilder.Diagnostic(
                    "prefab_mutation_failed",
                    "The transaction threw before the prefab asset was written; the asset is unchanged.",
                    exception.Message));
            }
            finally
            {
                if (contents != null)
                {
                    PrefabUtility.UnloadPrefabContents(contents);
                }
            }
        }

        internal static string ApplyOperations(
            XUUnityLightMcpPrefabMutationArgs args,
            GameObject contents,
            HashSet<string> allowed,
            XUUnityLightMcpPrefabMutationPayload payload)
        {
            return ApplyOperations(args.operations, contents, allowed, payload, false);
        }

        internal static string ApplyOperations(
            XUUnityLightMcpPrefabMutationOperation[] requested,
            GameObject contents,
            HashSet<string> allowed,
            XUUnityLightMcpPrefabMutationPayload payload,
            bool allowAnyComponentType)
        {
            var operations = requested ?? Array.Empty<XUUnityLightMcpPrefabMutationOperation>();
            for (var index = 0; index < operations.Length; index++)
            {
                var change = XUUnityLightMcpPrefabMutator.Apply(contents, operations[index], index, allowed, allowAnyComponentType);
                payload.changes.Add(change);
                if (string.Equals(change.status, "failed", StringComparison.Ordinal))
                {
                    return $"operation {index} ({change.op}) failed as {change.error_code}";
                }
            }

            return null;
        }

        internal static XUUnityLightMcpPrefabValidatePayload ValidateContents(
            GameObject contents,
            XUUnityLightMcpPrefabMutationPayload payload)
        {
            var validation = new XUUnityLightMcpPrefabValidatePayload
            {
                project_root = payload.project_root,
                generated_at_utc = payload.generated_at_utc,
                prefab_path = payload.prefab_path,
                prefab_guid = payload.prefab_guid,
                operation = "unity.prefab.validate"
            };

            XUUnityLightMcpPrefabInspector.Inspect(contents, false, validation);
            validation.defect_types = XUUnityLightMcpPrefabInspector.DistinctDefectTypes(validation.defects);
            var errorCount = 0;
            foreach (var defect in validation.defects)
            {
                if (string.Equals(defect.severity, "error", StringComparison.Ordinal))
                {
                    errorCount++;
                }
            }

            validation.passed = errorCount == 0;
            validation.status = validation.passed ? "passed" : "failed";
            validation.success = true;
            validation.proof_class = XUUnityLightMcpUiRead.ProofSemanticTree;
            return validation;
        }

        internal static string BuildReversiblePatch(XUUnityLightMcpPrefabMutationPayload payload)
        {
            var inverse = new List<string>();
            for (var index = payload.changes.Count - 1; index >= 0; index--)
            {
                var change = payload.changes[index];
                if (!string.Equals(change.status, "applied", StringComparison.Ordinal))
                {
                    continue;
                }

                inverse.Add(
                    "{"
                    + $"\"op\":\"{Escape(change.inverse_op)}\","
                    + $"\"path\":\"{Escape(change.object_path)}\","
                    + $"\"componentType\":\"{Escape(change.component_type)}\","
                    + $"\"propertyPath\":\"{Escape(change.property_path)}\","
                    + $"\"restoreValue\":\"{Escape(change.before)}\""
                    + "}");
            }

            return "{\"schema_version\":\"xuunity.prefab-mutation-patch.v1\",\"prefab_path\":\""
                   + Escape(payload.prefab_path)
                   + "\",\"sha256_before\":\""
                   + Escape(payload.sha256_before)
                   + "\",\"inverse_operations\":["
                   + string.Join(",", inverse)
                   + "]}";
        }

        internal static int CountStatus(List<XUUnityLightMcpPrefabMutationChange> changes, string status)
        {
            var count = 0;
            foreach (var change in changes)
            {
                if (string.Equals(change.status, status, StringComparison.Ordinal))
                {
                    count++;
                }
            }

            return count;
        }

        static string Escape(string value)
        {
            return (value ?? "").Replace("\\", "\\\\").Replace("\"", "\\\"");
        }

        internal static string FileSha256(string path)
        {
            try
            {
                using var stream = File.OpenRead(path);
                using var sha = SHA256.Create();
                return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
            }
            catch
            {
                return "";
            }
        }

        static XUUnityLightMcpResponse Respond(
            XUUnityLightMcpRequest request,
            XUUnityLightMcpPrefabMutationPayload payload)
        {
            return XUUnityLightMcpResponseWriter.Success(
                request.request_id,
                RegisteredOperationName,
                JsonUtility.ToJson(payload)
            );
        }
    }
}
