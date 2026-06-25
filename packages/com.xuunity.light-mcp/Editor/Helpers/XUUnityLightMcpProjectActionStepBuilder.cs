using System;
using System.Collections.Generic;
using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Helpers
{
    static class XUUnityLightMcpProjectActionStepBuilder
    {
        static readonly HashSet<string> ProjectActionStepKeys = new(StringComparer.Ordinal)
        {
            "kind",
            "actionId",
            "projectAction",
            "payload",
            "payloadJson",
            "allowMutating",
            "catalogPath",
        };

        public static bool TryBuildExecutableProjectActionStep(
            XUUnityLightMcpScenarioStepDefinition step,
            out XUUnityLightMcpScenarioStepDefinition executableStep,
            out string errorCode,
            out string errorMessage)
        {
            executableStep = null;
            errorCode = "";
            errorMessage = "";

            var actionId = ProjectActionCatalogLoader.NormalizeActionId(step?.actionId, step?.projectAction);
            if (string.IsNullOrWhiteSpace(actionId))
            {
                errorCode = "missing_project_action";
                errorMessage = "project_action step requires actionId or projectAction.";
                return false;
            }

            if (!ProjectActionCatalogLoader.TryLoad("", out var catalog, out errorCode, out errorMessage))
            {
                return false;
            }

            if (!catalog.TryResolve(actionId, out var action))
            {
                errorCode = "unknown_project_action";
                errorMessage = $"Project action '{actionId}' is not declared in project_actions.yaml.";
                return false;
            }

            if (action.Mutates.Count > 0 && step != null && !step.allowMutating)
            {
                errorCode = "project_action_mutation_approval_required";
                errorMessage = $"Scenario step invokes mutating project action '{action.ActionId}'. Set allowMutating=true after reviewing the project action catalog contract.";
                return false;
            }

            if (string.IsNullOrWhiteSpace(action.HookName))
            {
                errorCode = "project_action_hook_missing";
                errorMessage = $"Project action '{action.ActionId}' does not declare a hookName.";
                return false;
            }

            var payloadJson = string.IsNullOrWhiteSpace(step?.payloadJson) ? "{}" : step.payloadJson;
            if (!LightJsonNode.TryParse(payloadJson, out var payload, out errorMessage) || payload.Kind != LightJsonKind.Object)
            {
                errorCode = "project_action_payload_invalid";
                errorMessage = "project_action payloadJson must be a JSON object.";
                return false;
            }

            if (payload.TryGetString("action", out var payloadAction)
                && !string.IsNullOrWhiteSpace(payloadAction)
                && !string.Equals(payloadAction.Trim(), action.ActionId, StringComparison.Ordinal))
            {
                errorCode = "project_action_payload_reserved_key";
                errorMessage = "project_action payloadJson must not override the catalog action id.";
                return false;
            }

            payload.Object["action"] = LightJsonNode.String(action.ActionId);

            executableStep = new XUUnityLightMcpScenarioStepDefinition
            {
                stepId = step?.stepId ?? "",
                kind = "project_defined_hook",
                dependsOn = step?.dependsOn,
                runIfStepPassed = step?.runIfStepPassed,
                action = step?.action ?? "",
                durationSeconds = step?.durationSeconds ?? 0.0d,
                timeoutSeconds = step?.timeoutSeconds ?? 10.0d,
                expectedPlaymodeState = step?.expectedPlaymodeState ?? "",
                expectedName = step?.expectedName ?? "",
                expectedPath = step?.expectedPath ?? "",
                requiredRootNames = step?.requiredRootNames,
                allowDirty = step?.allowDirty ?? true,
                limit = step?.limit ?? 50,
                includeTypes = step?.includeTypes,
                fileName = step?.fileName ?? "",
                includeImage = step?.includeImage ?? false,
                maxResolution = step?.maxResolution ?? 640,
                target = step?.target ?? "",
                optionFlags = step?.optionFlags,
                extraDefines = step?.extraDefines,
                testNames = step?.testNames,
                groupNames = step?.groupNames,
                categoryNames = step?.categoryNames,
                assemblyNames = step?.assemblyNames,
                name = step?.name ?? "",
                width = step?.width ?? 0,
                height = step?.height ?? 0,
                group = step?.group ?? "",
                label = step?.label ?? "",
                allowCreateCustomSize = step?.allowCreateCustomSize ?? false,
                forceAssetRefresh = step?.forceAssetRefresh ?? true,
                resolvePackages = step?.resolvePackages ?? true,
                rerunHealthProbe = step?.rerunHealthProbe ?? true,
                hookName = action.HookName,
                hookPayloadJson = payload.ToJson(),
                actionId = action.ActionId,
                projectAction = action.ActionId,
                payloadJson = payload.ToJson(),
                allowMutating = step?.allowMutating ?? false,
            };
            return true;
        }

        public static bool TryNormalizeStepArray(
            LightJsonNode scenario,
            string arrayKey,
            ProjectActionCatalog catalog,
            out string errorCode,
            out string errorMessage)
        {
            errorCode = "";
            errorMessage = "";

            if (!scenario.TryGetArray(arrayKey, out var steps))
            {
                return true;
            }

            for (var i = 0; i < steps.Array.Count; i++)
            {
                var step = steps.Array[i];
                if (step.Kind != LightJsonKind.Object
                    || !string.Equals(step.GetString("kind"), "project_action", StringComparison.Ordinal))
                {
                    continue;
                }

                if (!TryNormalizeProjectActionStep(step, arrayKey, i, catalog, out errorCode, out errorMessage))
                {
                    return false;
                }
            }

            return true;
        }

        static bool TryNormalizeProjectActionStep(
            LightJsonNode step,
            string stepGroup,
            int stepIndex,
            ProjectActionCatalog catalog,
            out string errorCode,
            out string errorMessage)
        {
            errorCode = "";
            errorMessage = "";

            var stepId = step.GetString("stepId");
            if (string.IsNullOrWhiteSpace(stepId))
            {
                stepId = $"{stepGroup}_{stepIndex}";
            }

            var actionId = ProjectActionCatalogLoader.NormalizeActionId(step.GetString("actionId"), step.GetString("projectAction"));
            if (string.IsNullOrWhiteSpace(actionId))
            {
                errorCode = "missing_project_action";
                errorMessage = $"Scenario step '{stepId}' requires actionId or projectAction.";
                return false;
            }

            if (!catalog.TryResolve(actionId, out var action))
            {
                errorCode = "unknown_project_action";
                errorMessage = $"Project action '{actionId}' is not declared in project_actions.yaml.";
                return false;
            }

            if (action.Mutates.Count > 0 && !step.GetBool("allowMutating"))
            {
                errorCode = "project_action_mutation_approval_required";
                errorMessage = $"Scenario step '{stepId}' invokes mutating project action '{action.ActionId}'. Set allowMutating=true after reviewing the project action catalog contract.";
                return false;
            }

            if (step.Object.ContainsKey("hookName") || step.Object.ContainsKey("hookPayloadJson"))
            {
                errorCode = "project_action_step_reserved_key";
                errorMessage = "project_action scenario steps must not set hookName or hookPayloadJson directly.";
                return false;
            }

            if (string.IsNullOrWhiteSpace(action.HookName))
            {
                errorCode = "project_action_hook_missing";
                errorMessage = $"Project action '{action.ActionId}' does not declare a hookName.";
                return false;
            }

            if (!TryBuildHookPayload(step, action.ActionId, out var hookPayload, out errorCode, out errorMessage))
            {
                return false;
            }

            var replacement = LightJsonNode.ObjectNode();
            foreach (var pair in step.Object)
            {
                if (!ProjectActionStepKeys.Contains(pair.Key))
                {
                    replacement.Object[pair.Key] = pair.Value;
                }
            }

            replacement.Object["kind"] = LightJsonNode.String("project_defined_hook");
            replacement.Object["hookName"] = LightJsonNode.String(action.HookName);
            replacement.Object["hookPayloadJson"] = LightJsonNode.String(hookPayload.ToJson());

            step.ReplaceWith(replacement);
            return true;
        }

        static bool TryBuildHookPayload(
            LightJsonNode step,
            string canonicalActionId,
            out LightJsonNode hookPayload,
            out string errorCode,
            out string errorMessage)
        {
            hookPayload = LightJsonNode.ObjectNode();
            errorCode = "";
            errorMessage = "";

            if (step.Object.TryGetValue("payload", out var payload))
            {
                if (payload.Kind != LightJsonKind.Object)
                {
                    errorCode = "project_action_payload_invalid";
                    errorMessage = "project_action scenario step payload must be a JSON object.";
                    return false;
                }

                hookPayload = payload.Clone();
            }
            else if (step.TryGetString("payloadJson", out var payloadJson) && !string.IsNullOrWhiteSpace(payloadJson))
            {
                if (!LightJsonNode.TryParse(payloadJson, out hookPayload, out errorMessage) || hookPayload.Kind != LightJsonKind.Object)
                {
                    errorCode = "project_action_payload_invalid";
                    errorMessage = "project_action payloadJson must be a JSON object.";
                    return false;
                }
            }

            if (hookPayload.TryGetString("action", out var payloadAction)
                && !string.IsNullOrWhiteSpace(payloadAction)
                && !string.Equals(payloadAction.Trim(), canonicalActionId, StringComparison.Ordinal))
            {
                errorCode = "project_action_payload_reserved_key";
                errorMessage = "project_action scenario step payload must not override the catalog action id.";
                return false;
            }

            hookPayload.Object["action"] = LightJsonNode.String(canonicalActionId);
            return true;
        }
    }
}
