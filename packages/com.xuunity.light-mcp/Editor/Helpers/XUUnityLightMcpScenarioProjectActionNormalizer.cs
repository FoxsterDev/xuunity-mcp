using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Helpers
{
    internal static class XUUnityLightMcpScenarioProjectActionNormalizer
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

        public static bool TryNormalizeArgsJson(
            string argsJson,
            out string normalizedArgsJson,
            out string errorCode,
            out string errorMessage)
        {
            return TryNormalizeArgsJson(argsJson, "", out normalizedArgsJson, out errorCode, out errorMessage);
        }

        internal static bool TryNormalizeArgsJson(
            string argsJson,
            string explicitCatalogPath,
            out string normalizedArgsJson,
            out string errorCode,
            out string errorMessage)
        {
            normalizedArgsJson = argsJson;
            errorCode = "";
            errorMessage = "";

            if (string.IsNullOrWhiteSpace(argsJson))
            {
                return true;
            }

            if (!JsonNode.TryParse(argsJson, out var root, out errorMessage) || root.Kind != JsonKind.Object)
            {
                errorCode = "scenario_args_json_invalid";
                return false;
            }

            if (!root.TryGetObject("scenario", out var scenario))
            {
                return true;
            }

            var catalogPath = !string.IsNullOrWhiteSpace(explicitCatalogPath)
                ? explicitCatalogPath
                : root.GetString("catalogPath");

            if (!TryNormalizeScenario(scenario, catalogPath, out errorCode, out errorMessage))
            {
                return false;
            }

            normalizedArgsJson = root.ToJson();
            return true;
        }

        public static bool TryBuildExecutableProjectActionStep(
            XUUnityLightMcpScenarioStepDefinition step,
            out XUUnityLightMcpScenarioStepDefinition executableStep,
            out string errorCode,
            out string errorMessage)
        {
            executableStep = null;
            errorCode = "";
            errorMessage = "";

            var actionId = NormalizeActionId(step?.actionId, step?.projectAction);
            if (string.IsNullOrWhiteSpace(actionId))
            {
                errorCode = "missing_project_action";
                errorMessage = "project_action step requires actionId or projectAction.";
                return false;
            }

            if (!TryLoadCatalog("", out var catalog, out errorCode, out errorMessage))
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
            if (!JsonNode.TryParse(payloadJson, out var payload, out errorMessage) || payload.Kind != JsonKind.Object)
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

            payload.Object["action"] = JsonNode.String(action.ActionId);

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

        static bool TryNormalizeScenario(JsonNode scenario, string catalogPath, out string errorCode, out string errorMessage)
        {
            errorCode = "";
            errorMessage = "";

            if (!TryNormalizePollUntilStepArray(scenario, "steps", out errorCode, out errorMessage)
                || !TryNormalizePollUntilStepArray(scenario, "cleanupSteps", out errorCode, out errorMessage))
            {
                return false;
            }

            var hasProjectAction = HasProjectActionSteps(scenario);
            if (!hasProjectAction)
            {
                return true;
            }

            if (!TryLoadCatalog(catalogPath, out var catalog, out errorCode, out errorMessage))
            {
                return false;
            }

            return TryNormalizeStepArray(scenario, "steps", catalog, out errorCode, out errorMessage)
                && TryNormalizeStepArray(scenario, "cleanupSteps", catalog, out errorCode, out errorMessage);
        }

        static bool TryNormalizePollUntilStepArray(
            JsonNode scenario,
            string arrayKey,
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
                if (step.Kind != JsonKind.Object)
                {
                    continue;
                }

                var operation = step.GetString("kind");
                if (string.IsNullOrWhiteSpace(operation))
                {
                    operation = step.GetString("operation");
                    if (!string.IsNullOrWhiteSpace(operation))
                    {
                        step.Object["kind"] = JsonNode.String(operation);
                    }
                }

                if (!string.Equals(operation, "project_defined_hook_poll_until", StringComparison.Ordinal))
                {
                    continue;
                }

                if (!TryPromoteObjectPayloadToJsonString(step, "startPayload", "startPayloadJson", out errorCode, out errorMessage)
                    || !TryPromoteObjectPayloadToJsonString(step, "pollPayload", "pollPayloadJson", out errorCode, out errorMessage))
                {
                    return false;
                }
            }

            return true;
        }

        static bool TryPromoteObjectPayloadToJsonString(
            JsonNode step,
            string objectKey,
            string jsonKey,
            out string errorCode,
            out string errorMessage)
        {
            errorCode = "";
            errorMessage = "";

            if (step.Object.ContainsKey(jsonKey) || !step.Object.TryGetValue(objectKey, out var payload))
            {
                return true;
            }

            if (payload.Kind != JsonKind.Object)
            {
                errorCode = $"poll_until_{objectKey}_invalid";
                errorMessage = $"project_defined_hook_poll_until {objectKey} must be a JSON object.";
                return false;
            }

            step.Object[jsonKey] = JsonNode.String(payload.ToJson());
            step.Object.Remove(objectKey);
            return true;
        }

        static bool HasProjectActionSteps(JsonNode scenario)
        {
            return HasProjectActionSteps(scenario, "steps") || HasProjectActionSteps(scenario, "cleanupSteps");
        }

        static bool HasProjectActionSteps(JsonNode scenario, string arrayKey)
        {
            if (!scenario.TryGetArray(arrayKey, out var steps))
            {
                return false;
            }

            return steps.Array.Any(step => step.Kind == JsonKind.Object
                && string.Equals(step.GetString("kind"), "project_action", StringComparison.Ordinal));
        }

        static bool TryNormalizeStepArray(
            JsonNode scenario,
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
                if (step.Kind != JsonKind.Object
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
            JsonNode step,
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

            var actionId = NormalizeActionId(step.GetString("actionId"), step.GetString("projectAction"));
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

            var replacement = JsonNode.ObjectNode();
            foreach (var pair in step.Object)
            {
                if (!ProjectActionStepKeys.Contains(pair.Key))
                {
                    replacement.Object[pair.Key] = pair.Value;
                }
            }

            replacement.Object["kind"] = JsonNode.String("project_defined_hook");
            replacement.Object["hookName"] = JsonNode.String(action.HookName);
            replacement.Object["hookPayloadJson"] = JsonNode.String(hookPayload.ToJson());

            step.ReplaceWith(replacement);
            return true;
        }

        static bool TryBuildHookPayload(
            JsonNode step,
            string canonicalActionId,
            out JsonNode hookPayload,
            out string errorCode,
            out string errorMessage)
        {
            hookPayload = JsonNode.ObjectNode();
            errorCode = "";
            errorMessage = "";

            if (step.Object.TryGetValue("payload", out var payload))
            {
                if (payload.Kind != JsonKind.Object)
                {
                    errorCode = "project_action_payload_invalid";
                    errorMessage = "project_action scenario step payload must be a JSON object.";
                    return false;
                }

                hookPayload = payload.Clone();
            }
            else if (step.TryGetString("payloadJson", out var payloadJson) && !string.IsNullOrWhiteSpace(payloadJson))
            {
                if (!JsonNode.TryParse(payloadJson, out hookPayload, out errorMessage) || hookPayload.Kind != JsonKind.Object)
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

            hookPayload.Object["action"] = JsonNode.String(canonicalActionId);
            return true;
        }

        static bool TryLoadCatalog(
            string catalogPath,
            out ProjectActionCatalog catalog,
            out string errorCode,
            out string errorMessage)
        {
            catalog = null;
            errorCode = "";
            errorMessage = "";

            var resolvedPath = ResolveCatalogPath(catalogPath);
            if (string.IsNullOrWhiteSpace(resolvedPath) || !File.Exists(resolvedPath))
            {
                errorCode = "project_action_catalog_not_found";
                errorMessage = "Could not find project_actions.yaml for Unity-native project_action scenario steps.";
                return false;
            }

            try
            {
                catalog = ParseProjectActionCatalog(File.ReadAllLines(resolvedPath));
                catalog.CatalogPath = resolvedPath;
            }
            catch (Exception ex)
            {
                errorCode = "project_actions_yaml_invalid";
                errorMessage = ex.Message;
                return false;
            }

            if (catalog.Actions.Count == 0)
            {
                errorCode = "project_action_catalog_empty";
                errorMessage = $"Project action catalog does not declare any actions: {resolvedPath}";
                return false;
            }

            return true;
        }

        static string ResolveCatalogPath(string catalogPath)
        {
            var projectRoot = XUUnityLightMcpFileIpcPaths.ProjectRootPath;
            if (!string.IsNullOrWhiteSpace(catalogPath))
            {
                var explicitPath = catalogPath.Trim();
                if (!Path.IsPathRooted(explicitPath))
                {
                    explicitPath = Path.GetFullPath(Path.Combine(projectRoot, explicitPath));
                }

                return explicitPath;
            }

            var projectName = new DirectoryInfo(projectRoot).Name;
            var workspaceRoot = Directory.GetParent(projectRoot)?.FullName ?? projectRoot;
            var candidates = new[]
            {
                Path.Combine(workspaceRoot, "AIOutput", "Projects", projectName, "Operations", "XUUnityLightUnityMcp", "project_actions.yaml"),
                Path.Combine(projectRoot, "AIOutput", "Operations", "XUUnityLightUnityMcp", "project_actions.yaml"),
                Path.Combine(projectRoot, "Assets", "AIOutput", "Operations", "XUUnityLightUnityMcp", "project_actions.yaml"),
            };

            return candidates.FirstOrDefault(File.Exists) ?? candidates[0];
        }

        static ProjectActionCatalog ParseProjectActionCatalog(string[] lines)
        {
            var catalog = new ProjectActionCatalog();
            ProjectActionRecord currentAction = null;
            var inActions = false;
            var listField = "";

            foreach (var rawLine in lines ?? Array.Empty<string>())
            {
                if (string.IsNullOrWhiteSpace(rawLine))
                {
                    continue;
                }

                var trimmed = rawLine.Trim();
                if (trimmed.StartsWith("#", StringComparison.Ordinal))
                {
                    continue;
                }

                var indent = CountLeadingSpaces(rawLine);
                if (indent == 0)
                {
                    currentAction = null;
                    listField = "";
                    if (trimmed == "actions:")
                    {
                        inActions = true;
                        continue;
                    }

                    if (!inActions && TryReadKeyValue(trimmed, out var rootKey, out var rootValue)
                        && string.Equals(rootKey, "hookName", StringComparison.Ordinal))
                    {
                        catalog.DefaultHookName = NormalizeYamlScalar(rootValue);
                    }

                    continue;
                }

                if (!inActions)
                {
                    continue;
                }

                if (indent == 2 && trimmed.EndsWith(":", StringComparison.Ordinal))
                {
                    var actionId = trimmed.Substring(0, trimmed.Length - 1).Trim();
                    currentAction = new ProjectActionRecord { ActionId = actionId };
                    catalog.Actions.Add(currentAction);
                    listField = "";
                    continue;
                }

                if (currentAction == null)
                {
                    continue;
                }

                if (indent == 4 && TryReadKeyValue(trimmed, out var key, out var value))
                {
                    listField = "";
                    if (string.Equals(key, "hookName", StringComparison.Ordinal))
                    {
                        currentAction.HookName = NormalizeYamlScalar(value);
                    }
                    else if (string.Equals(key, "aliases", StringComparison.Ordinal)
                        || string.Equals(key, "mutates", StringComparison.Ordinal))
                    {
                        listField = key;
                        foreach (var item in ParseInlineList(value))
                        {
                            AddListItem(currentAction, key, item);
                        }
                    }

                    continue;
                }

                if (indent >= 6 && trimmed.StartsWith("-", StringComparison.Ordinal) && !string.IsNullOrWhiteSpace(listField))
                {
                    AddListItem(currentAction, listField, NormalizeYamlScalar(trimmed.Substring(1).Trim()));
                }
            }

            foreach (var action in catalog.Actions)
            {
                if (string.IsNullOrWhiteSpace(action.HookName))
                {
                    action.HookName = catalog.DefaultHookName;
                }
            }

            return catalog;
        }

        static bool TryReadKeyValue(string text, out string key, out string value)
        {
            key = "";
            value = "";
            var index = text.IndexOf(':');
            if (index < 0)
            {
                return false;
            }

            key = text.Substring(0, index).Trim();
            value = text.Substring(index + 1).Trim();
            return !string.IsNullOrWhiteSpace(key);
        }

        static void AddListItem(ProjectActionRecord action, string key, string item)
        {
            if (string.IsNullOrWhiteSpace(item))
            {
                return;
            }

            if (string.Equals(key, "aliases", StringComparison.Ordinal))
            {
                action.Aliases.Add(item);
            }
            else if (string.Equals(key, "mutates", StringComparison.Ordinal))
            {
                action.Mutates.Add(item);
            }
        }

        static IEnumerable<string> ParseInlineList(string value)
        {
            value = value?.Trim() ?? "";
            if (!value.StartsWith("[", StringComparison.Ordinal) || !value.EndsWith("]", StringComparison.Ordinal))
            {
                yield break;
            }

            var content = value.Substring(1, value.Length - 2).Trim();
            if (string.IsNullOrWhiteSpace(content))
            {
                yield break;
            }

            foreach (var part in content.Split(','))
            {
                var item = NormalizeYamlScalar(part.Trim());
                if (!string.IsNullOrWhiteSpace(item))
                {
                    yield return item;
                }
            }
        }

        static string NormalizeYamlScalar(string value)
        {
            value = value?.Trim() ?? "";
            if (value.Length >= 2
                && ((value[0] == '"' && value[value.Length - 1] == '"')
                    || (value[0] == '\'' && value[value.Length - 1] == '\'')))
            {
                return value.Substring(1, value.Length - 2);
            }

            return value;
        }

        static string NormalizeActionId(string actionId, string projectAction)
        {
            return !string.IsNullOrWhiteSpace(actionId)
                ? actionId.Trim()
                : (projectAction ?? "").Trim();
        }

        static int CountLeadingSpaces(string value)
        {
            var count = 0;
            while (count < value.Length && value[count] == ' ')
            {
                count++;
            }

            return count;
        }

        sealed class ProjectActionCatalog
        {
            public string CatalogPath = "";
            public string DefaultHookName = "";
            public readonly List<ProjectActionRecord> Actions = new();

            public bool TryResolve(string requestedAction, out ProjectActionRecord action)
            {
                action = null;
                var trimmed = (requestedAction ?? "").Trim();
                var matches = Actions
                    .Where(candidate => string.Equals(candidate.ActionId, trimmed, StringComparison.Ordinal)
                        || candidate.Aliases.Any(alias => string.Equals(alias, trimmed, StringComparison.Ordinal)))
                    .ToList();

                if (matches.Count == 1)
                {
                    action = matches[0];
                    return true;
                }

                return false;
            }
        }

        sealed class ProjectActionRecord
        {
            public string ActionId = "";
            public string HookName = "";
            public readonly List<string> Aliases = new();
            public readonly List<string> Mutates = new();
        }

        enum JsonKind
        {
            Null,
            Object,
            Array,
            String,
            Number,
            Bool,
        }

        sealed class JsonNode
        {
            public JsonKind Kind;
            public Dictionary<string, JsonNode> Object;
            public List<JsonNode> Array;
            public string StringValue;
            public string NumberValue;
            public bool BoolValue;

            public static JsonNode ObjectNode() => new() { Kind = JsonKind.Object, Object = new Dictionary<string, JsonNode>(StringComparer.Ordinal) };
            public static JsonNode ArrayNode() => new() { Kind = JsonKind.Array, Array = new List<JsonNode>() };
            public static JsonNode String(string value) => new() { Kind = JsonKind.String, StringValue = value ?? "" };

            public static bool TryParse(string json, out JsonNode node, out string errorMessage)
            {
                node = null;
                errorMessage = "";

                try
                {
                    var parser = new JsonParser(json ?? "");
                    node = parser.Parse();
                    return true;
                }
                catch (Exception ex)
                {
                    errorMessage = ex.Message;
                    return false;
                }
            }

            public bool TryGetObject(string key, out JsonNode value)
            {
                return TryGet(key, JsonKind.Object, out value);
            }

            public bool TryGetArray(string key, out JsonNode value)
            {
                return TryGet(key, JsonKind.Array, out value);
            }

            public bool TryGetString(string key, out string value)
            {
                value = "";
                if (Kind != JsonKind.Object
                    || Object == null
                    || !Object.TryGetValue(key, out var node)
                    || node.Kind != JsonKind.String)
                {
                    return false;
                }

                value = node.StringValue ?? "";
                return true;
            }

            public string GetString(string key)
            {
                return TryGetString(key, out var value) ? value : "";
            }

            public bool GetBool(string key)
            {
                return Kind == JsonKind.Object
                    && Object != null
                    && Object.TryGetValue(key, out var node)
                    && node.Kind == JsonKind.Bool
                    && node.BoolValue;
            }

            public JsonNode Clone()
            {
                switch (Kind)
                {
                    case JsonKind.Object:
                    {
                        var clone = ObjectNode();
                        foreach (var pair in Object)
                        {
                            clone.Object[pair.Key] = pair.Value.Clone();
                        }

                        return clone;
                    }
                    case JsonKind.Array:
                    {
                        var clone = ArrayNode();
                        foreach (var item in Array)
                        {
                            clone.Array.Add(item.Clone());
                        }

                        return clone;
                    }
                    case JsonKind.String:
                        return String(StringValue);
                    case JsonKind.Number:
                        return new JsonNode { Kind = JsonKind.Number, NumberValue = NumberValue };
                    case JsonKind.Bool:
                        return new JsonNode { Kind = JsonKind.Bool, BoolValue = BoolValue };
                    default:
                        return new JsonNode { Kind = JsonKind.Null };
                }
            }

            public void ReplaceWith(JsonNode replacement)
            {
                Kind = replacement.Kind;
                Object = replacement.Object;
                Array = replacement.Array;
                StringValue = replacement.StringValue;
                NumberValue = replacement.NumberValue;
                BoolValue = replacement.BoolValue;
            }

            public string ToJson()
            {
                var builder = new StringBuilder();
                WriteJson(builder);
                return builder.ToString();
            }

            bool TryGet(string key, JsonKind expectedKind, out JsonNode value)
            {
                value = null;
                return Kind == JsonKind.Object
                    && Object != null
                    && Object.TryGetValue(key, out value)
                    && value.Kind == expectedKind;
            }

            void WriteJson(StringBuilder builder)
            {
                switch (Kind)
                {
                    case JsonKind.Object:
                        builder.Append('{');
                        var firstProperty = true;
                        foreach (var pair in Object)
                        {
                            if (!firstProperty)
                            {
                                builder.Append(',');
                            }

                            WriteEscapedString(builder, pair.Key);
                            builder.Append(':');
                            pair.Value.WriteJson(builder);
                            firstProperty = false;
                        }

                        builder.Append('}');
                        break;
                    case JsonKind.Array:
                        builder.Append('[');
                        for (var i = 0; i < Array.Count; i++)
                        {
                            if (i > 0)
                            {
                                builder.Append(',');
                            }

                            Array[i].WriteJson(builder);
                        }

                        builder.Append(']');
                        break;
                    case JsonKind.String:
                        WriteEscapedString(builder, StringValue ?? "");
                        break;
                    case JsonKind.Number:
                        builder.Append(NumberValue);
                        break;
                    case JsonKind.Bool:
                        builder.Append(BoolValue ? "true" : "false");
                        break;
                    default:
                        builder.Append("null");
                        break;
                }
            }

            static void WriteEscapedString(StringBuilder builder, string value)
            {
                builder.Append('"');
                foreach (var c in value ?? "")
                {
                    switch (c)
                    {
                        case '"':
                            builder.Append("\\\"");
                            break;
                        case '\\':
                            builder.Append("\\\\");
                            break;
                        case '\b':
                            builder.Append("\\b");
                            break;
                        case '\f':
                            builder.Append("\\f");
                            break;
                        case '\n':
                            builder.Append("\\n");
                            break;
                        case '\r':
                            builder.Append("\\r");
                            break;
                        case '\t':
                            builder.Append("\\t");
                            break;
                        default:
                            if (c < 32 || c > 126)
                            {
                                builder.Append("\\u");
                                builder.Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                            }
                            else
                            {
                                builder.Append(c);
                            }
                            break;
                    }
                }

                builder.Append('"');
            }
        }

        sealed class JsonParser
        {
            readonly string _json;
            int _index;

            public JsonParser(string json)
            {
                _json = json ?? "";
            }

            public JsonNode Parse()
            {
                SkipWhitespace();
                var value = ParseValue();
                SkipWhitespace();
                if (_index != _json.Length)
                {
                    throw Error("Unexpected trailing JSON content.");
                }

                return value;
            }

            JsonNode ParseValue()
            {
                SkipWhitespace();
                if (_index >= _json.Length)
                {
                    throw Error("Unexpected end of JSON.");
                }

                var c = _json[_index];
                return c switch
                {
                    '{' => ParseObject(),
                    '[' => ParseArray(),
                    '"' => JsonNode.String(ParseString()),
                    't' => ParseLiteral("true", new JsonNode { Kind = JsonKind.Bool, BoolValue = true }),
                    'f' => ParseLiteral("false", new JsonNode { Kind = JsonKind.Bool, BoolValue = false }),
                    'n' => ParseLiteral("null", new JsonNode { Kind = JsonKind.Null }),
                    '-' or >= '0' and <= '9' => ParseNumber(),
                    _ => throw Error($"Unexpected JSON character '{c}'."),
                };
            }

            JsonNode ParseObject()
            {
                Expect('{');
                var node = JsonNode.ObjectNode();
                SkipWhitespace();
                if (TryConsume('}'))
                {
                    return node;
                }

                while (true)
                {
                    SkipWhitespace();
                    var key = ParseString();
                    SkipWhitespace();
                    Expect(':');
                    node.Object[key] = ParseValue();
                    SkipWhitespace();
                    if (TryConsume('}'))
                    {
                        return node;
                    }

                    Expect(',');
                }
            }

            JsonNode ParseArray()
            {
                Expect('[');
                var node = JsonNode.ArrayNode();
                SkipWhitespace();
                if (TryConsume(']'))
                {
                    return node;
                }

                while (true)
                {
                    node.Array.Add(ParseValue());
                    SkipWhitespace();
                    if (TryConsume(']'))
                    {
                        return node;
                    }

                    Expect(',');
                }
            }

            JsonNode ParseNumber()
            {
                var start = _index;
                if (Peek('-'))
                {
                    _index++;
                }

                ReadDigits();
                if (Peek('.'))
                {
                    _index++;
                    ReadDigits();
                }

                if (Peek('e') || Peek('E'))
                {
                    _index++;
                    if (Peek('+') || Peek('-'))
                    {
                        _index++;
                    }

                    ReadDigits();
                }

                return new JsonNode
                {
                    Kind = JsonKind.Number,
                    NumberValue = _json.Substring(start, _index - start),
                };
            }

            JsonNode ParseLiteral(string literal, JsonNode value)
            {
                if (_index + literal.Length > _json.Length
                    || !string.Equals(_json.Substring(_index, literal.Length), literal, StringComparison.Ordinal))
                {
                    throw Error($"Expected JSON literal '{literal}'.");
                }

                _index += literal.Length;
                return value;
            }

            string ParseString()
            {
                Expect('"');
                var builder = new StringBuilder();
                while (_index < _json.Length)
                {
                    var c = _json[_index++];
                    if (c == '"')
                    {
                        return builder.ToString();
                    }

                    if (c != '\\')
                    {
                        builder.Append(c);
                        continue;
                    }

                    if (_index >= _json.Length)
                    {
                        throw Error("Unterminated JSON string escape.");
                    }

                    var escaped = _json[_index++];
                    switch (escaped)
                    {
                        case '"':
                        case '\\':
                        case '/':
                            builder.Append(escaped);
                            break;
                        case 'b':
                            builder.Append('\b');
                            break;
                        case 'f':
                            builder.Append('\f');
                            break;
                        case 'n':
                            builder.Append('\n');
                            break;
                        case 'r':
                            builder.Append('\r');
                            break;
                        case 't':
                            builder.Append('\t');
                            break;
                        case 'u':
                            builder.Append(ParseUnicodeEscape());
                            break;
                        default:
                            throw Error($"Unsupported JSON string escape '\\{escaped}'.");
                    }
                }

                throw Error("Unterminated JSON string.");
            }

            char ParseUnicodeEscape()
            {
                if (_index + 4 > _json.Length)
                {
                    throw Error("Incomplete JSON unicode escape.");
                }

                var hex = _json.Substring(_index, 4);
                if (!int.TryParse(hex, NumberStyles.HexNumber, CultureInfo.InvariantCulture, out var codePoint))
                {
                    throw Error("Invalid JSON unicode escape.");
                }

                _index += 4;
                return (char)codePoint;
            }

            void ReadDigits()
            {
                var start = _index;
                while (_index < _json.Length && _json[_index] >= '0' && _json[_index] <= '9')
                {
                    _index++;
                }

                if (_index == start)
                {
                    throw Error("Expected JSON number digit.");
                }
            }

            bool Peek(char c)
            {
                return _index < _json.Length && _json[_index] == c;
            }

            bool TryConsume(char c)
            {
                if (!Peek(c))
                {
                    return false;
                }

                _index++;
                return true;
            }

            void Expect(char c)
            {
                if (!TryConsume(c))
                {
                    throw Error($"Expected JSON character '{c}'.");
                }
            }

            void SkipWhitespace()
            {
                while (_index < _json.Length && char.IsWhiteSpace(_json[_index]))
                {
                    _index++;
                }
            }

            Exception Error(string message)
            {
                return new FormatException($"{message} At offset {_index}.");
            }
        }
    }
}
