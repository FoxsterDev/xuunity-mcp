using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Helpers
{
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

    static class ProjectActionCatalogLoader
    {
        public static bool TryLoad(
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

        public static string NormalizeActionId(string actionId, string projectAction)
        {
            return !string.IsNullOrWhiteSpace(actionId)
                ? actionId.Trim()
                : (projectAction ?? "").Trim();
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

        static int CountLeadingSpaces(string value)
        {
            var count = 0;
            while (count < value.Length && value[count] == ' ')
            {
                count++;
            }

            return count;
        }
    }
}
