using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using UnityEditor;
using UnityEngine;
using XUUnity.LightMcp.Editor.Bridge;
using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Helpers
{
    internal static class XUUnityLightMcpProjectActionCurrency
    {
        const string DomainLoadCurrencyBasis = "editor_domain_load_vs_newest_assets_editor_input";
        const string SettledForcedAssetRefreshCurrencyBasis = "settled_forced_asset_refresh_covers_newest_assets_editor_input";
        internal const string ContentSnapshotCurrencyBasis = "compiled_editor_input_content_snapshot";

        static readonly HashSet<string> EditorInputExtensions = new(StringComparer.OrdinalIgnoreCase)
        {
            ".cs",
            ".asmdef",
            ".asmref",
            ".rsp",
        };

        public static XUUnityLightMcpProjectActionCurrencyPayload Capture(
            string actionId = "",
            string catalogPath = "",
            bool requiresFreshAssets = false,
            bool assetRefreshPerformed = false,
            string assetRefreshStepId = "")
        {
            var payload = new XUUnityLightMcpProjectActionCurrencyPayload
            {
                project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                action_id = actionId ?? "",
                catalog_path = catalogPath ?? "",
                requires_fresh_assets = requiresFreshAssets,
                asset_refresh_performed = assetRefreshPerformed,
                asset_refresh_step_id = assetRefreshStepId ?? "",
                editor_domain_loaded_utc = XUUnityLightMcpBridgeRuntimeState.EditorDomainLoadedUtc,
                application_run_in_background = Application.runInBackground,
                native_autofocus_enabled = false,
                background_execution_mode = XUUnityLightMcpBackgroundExecution.Mode,
            };

            var content = XUUnityLightMcpEditorInputSnapshot.Compare(XUUnityLightMcpFileIpcPaths.ProjectRootPath);
            bool scanSucceeded;
            string newestPath;
            string newestWriteUtc;
            int inputCount;
            var scanError = "";
            if (content.state == XUUnityLightMcpEditorInputSnapshot.StateFailed)
            {
                scanSucceeded = TryFindNewestEditorInput(
                    Path.Combine(XUUnityLightMcpFileIpcPaths.ProjectRootPath, "Assets"),
                    out newestPath,
                    out newestWriteUtc,
                    out inputCount,
                    out scanError);
            }
            else
            {
                scanSucceeded = true;
                newestPath = content.newest_path;
                newestWriteUtc = content.newest_write_utc;
                inputCount = content.input_count;
            }

            payload.newest_editor_input_path = newestPath;
            payload.newest_editor_input_write_utc = newestWriteUtc;
            payload.editor_input_count = inputCount;
            payload.editor_input_content_state = content.state;
            payload.editor_input_content_basis_utc = content.basis_utc;
            payload.changed_editor_input_count = content.changed_count;
            payload.changed_editor_inputs = content.changed_paths.ToArray();
            payload.script_compilation_failed = EditorUtility.scriptCompilationFailed;
            payload.settled_forced_asset_refresh_requested_utc =
                XUUnityLightMcpBridgeRuntimeState.SettledForcedAssetRefreshRequestedUtc;
            payload.editor_domain_currency = ClassifyEditorDomainCurrency(
                payload.editor_domain_loaded_utc,
                newestWriteUtc,
                scanSucceeded,
                payload.settled_forced_asset_refresh_requested_utc,
                payload.script_compilation_failed,
                content.state,
                content.changed_count,
                out var editorDomainCurrent,
                out var currencyKnown,
                out var currencyReason,
                out var currencyBasis);
            payload.editor_domain_current = editorDomainCurrent;
            payload.editor_domain_currency_known = currencyKnown;
            payload.currency_basis = currencyBasis;

            if (!scanSucceeded)
            {
                currencyReason = string.IsNullOrWhiteSpace(scanError)
                    ? "editor_input_scan_failed"
                    : $"editor_input_scan_failed:{scanError}";
            }

            var assetsCurrent = !requiresFreshAssets || assetRefreshPerformed;
            payload.safe_to_invoke = currencyKnown && editorDomainCurrent && assetsCurrent;
            if (!currencyKnown)
            {
                payload.reason = currencyReason;
                payload.recommended_next_action = "run_unity_project_refresh_before_invoking";
            }
            else if (!editorDomainCurrent)
            {
                payload.reason = currencyReason;
                payload.recommended_next_action = payload.script_compilation_failed
                    ? "fix_script_compilation_errors_before_invoking"
                    : "run_unity_project_refresh_before_invoking";
            }
            else if (!assetsCurrent)
            {
                payload.reason = "catalog_requires_fresh_assets_without_completed_refresh";
                payload.recommended_next_action = "run_automatic_project_refresh_before_invoking";
            }
            else
            {
                payload.reason = currencyReason;
                payload.recommended_next_action = "none";
            }

            return payload;
        }

        public static string ClassifyEditorDomainCurrency(
            string editorDomainLoadedUtc,
            string newestEditorInputWriteUtc,
            bool scanSucceeded,
            string settledForcedAssetRefreshRequestedUtc,
            bool scriptCompilationFailed,
            out bool editorDomainCurrent,
            out bool currencyKnown,
            out string reason,
            out string currencyBasis)
        {
            return ClassifyEditorDomainCurrency(
                editorDomainLoadedUtc,
                newestEditorInputWriteUtc,
                scanSucceeded,
                settledForcedAssetRefreshRequestedUtc,
                scriptCompilationFailed,
                XUUnityLightMcpEditorInputSnapshot.StateUnavailable,
                0,
                out editorDomainCurrent,
                out currencyKnown,
                out reason,
                out currencyBasis);
        }

        public static string ClassifyEditorDomainCurrency(
            string editorDomainLoadedUtc,
            string newestEditorInputWriteUtc,
            bool scanSucceeded,
            string settledForcedAssetRefreshRequestedUtc,
            bool scriptCompilationFailed,
            string contentState,
            int changedInputCount,
            out bool editorDomainCurrent,
            out bool currencyKnown,
            out string reason,
            out string currencyBasis)
        {
            if (scanSucceeded
                && string.Equals(contentState, XUUnityLightMcpEditorInputSnapshot.StateReady, StringComparison.Ordinal)
                && (changedInputCount > 0 || !scriptCompilationFailed))
            {
                currencyKnown = true;
                currencyBasis = ContentSnapshotCurrencyBasis;
                if (changedInputCount > 0)
                {
                    editorDomainCurrent = false;
                    reason = scriptCompilationFailed
                        ? "editor_input_content_changed_since_compile_with_failed_script_compilation"
                        : "editor_input_content_changed_since_compile";
                    return "stale";
                }

                editorDomainCurrent = true;
                reason = TryParseUtc(newestEditorInputWriteUtc, out var newestUtc)
                    && TryParseUtc(editorDomainLoadedUtc, out var loadedUtc)
                    && newestUtc > loadedUtc
                        ? "editor_inputs_touched_without_content_change"
                        : "editor_input_content_matches_compiled_snapshot";
                return "current";
            }

            editorDomainCurrent = false;
            currencyKnown = false;
            reason = "";
            currencyBasis = DomainLoadCurrencyBasis;
            if (!scanSucceeded)
            {
                reason = "editor_input_scan_failed";
                return "unknown";
            }

            if (!TryParseUtc(editorDomainLoadedUtc, out var domainLoadedUtc))
            {
                reason = "editor_domain_load_time_unavailable";
                return "unknown";
            }

            if (string.IsNullOrWhiteSpace(newestEditorInputWriteUtc))
            {
                editorDomainCurrent = true;
                currencyKnown = true;
                reason = "no_editor_domain_inputs_under_assets";
                return "current";
            }

            if (!TryParseUtc(newestEditorInputWriteUtc, out var newestInputUtc))
            {
                reason = "newest_editor_input_time_invalid";
                return "unknown";
            }

            currencyKnown = true;
            if (newestInputUtc <= domainLoadedUtc)
            {
                editorDomainCurrent = true;
                reason = "editor_domain_loaded_after_newest_assets_input";
                return "current";
            }

            if (!scriptCompilationFailed
                && TryParseUtc(settledForcedAssetRefreshRequestedUtc, out var forcedRefreshRequestedUtc)
                && newestInputUtc <= forcedRefreshRequestedUtc)
            {
                editorDomainCurrent = true;
                currencyBasis = SettledForcedAssetRefreshCurrencyBasis;
                reason = "settled_forced_asset_refresh_after_newest_assets_input_without_script_reload";
                return "current";
            }

            reason = scriptCompilationFailed
                ? "assets_editor_input_newer_than_loaded_editor_domain_with_failed_script_compilation"
                : "assets_editor_input_newer_than_loaded_editor_domain";
            return "stale";
        }

        internal static bool TryFindNewestEditorInput(
            string assetsRoot,
            out string newestPath,
            out string newestWriteUtc,
            out int inputCount,
            out string error)
        {
            newestPath = "";
            newestWriteUtc = "";
            inputCount = 0;
            error = "";
            if (string.IsNullOrEmpty(assetsRoot) || !Directory.Exists(assetsRoot))
            {
                return true;
            }

            try
            {
                var newestUtc = DateTime.MinValue;
                var pendingDirectories = new Stack<string>();
                pendingDirectories.Push(assetsRoot);
                while (pendingDirectories.Count > 0)
                {
                    var currentDirectory = pendingDirectories.Pop();
                    foreach (var childDirectory in Directory.EnumerateDirectories(currentDirectory))
                    {
                        if (IsUnityIgnoredEntryName(Path.GetFileName(childDirectory)))
                        {
                            continue;
                        }

                        pendingDirectories.Push(childDirectory);
                    }

                    foreach (var path in Directory.EnumerateFiles(currentDirectory))
                    {
                        if (!EditorInputExtensions.Contains(Path.GetExtension(path))
                            || IsUnityIgnoredEntryName(Path.GetFileName(path)))
                        {
                            continue;
                        }

                        inputCount++;
                        var writeUtc = File.GetLastWriteTimeUtc(path);
                        if (writeUtc <= newestUtc)
                        {
                            continue;
                        }

                        newestUtc = writeUtc;
                        newestPath = MakeProjectRelative(path);
                    }
                }

                if (newestUtc != DateTime.MinValue)
                {
                    newestWriteUtc = newestUtc.ToString("O", CultureInfo.InvariantCulture);
                }

                return true;
            }
            catch (Exception ex)
            {
                error = ex.GetType().Name;
                return false;
            }
        }

        internal static bool IsUnityIgnoredEntryName(string name)
        {
            if (string.IsNullOrEmpty(name))
            {
                return false;
            }

            if (name[0] == '.' || name[name.Length - 1] == '~')
            {
                return true;
            }

            return name.Length == 3
                && (name[0] == 'c' || name[0] == 'C')
                && (name[1] == 'v' || name[1] == 'V')
                && (name[2] == 's' || name[2] == 'S');
        }

        static string MakeProjectRelative(string path)
        {
            var projectRoot = XUUnityLightMcpFileIpcPaths.ProjectRootPath.TrimEnd(
                Path.DirectorySeparatorChar,
                Path.AltDirectorySeparatorChar);
            var prefix = projectRoot + Path.DirectorySeparatorChar;
            var relative = path.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)
                ? path.Substring(prefix.Length)
                : path;
            return relative.Replace('\\', '/');
        }

        static bool TryParseUtc(string value, out DateTime utc)
        {
            return DateTime.TryParse(
                value,
                CultureInfo.InvariantCulture,
                DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal,
                out utc);
        }
    }
}
