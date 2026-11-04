using System;
using System.Collections.Generic;
using UnityEngine;

namespace XUUnity.LightMcp.Editor.ScenarioHooks
{
    [Serializable]
    public sealed class XUUnityLightMcpMutationDelta
    {
        public const string SchemaVersion = "xuunity.mutation-delta.v1";

        public string schema_version = SchemaVersion;
        public string unit = "";
        public string target = "";
        public int before_count;
        public int after_count;
        public int added_count;
        public int removed_count;
        public int changed_count;

        public static XUUnityLightMcpMutationDelta FromWrittenAssets(
            IEnumerable<string> writtenAssetPaths,
            IEnumerable<string> createdAssetPaths = null,
            IEnumerable<string> changedPrefsKeys = null)
        {
            var created = Distinct(createdAssetPaths);
            var changed = Distinct(writtenAssetPaths);
            changed.ExceptWith(created);
            var prefs = Distinct(changedPrefsKeys);
            var unit = prefs.Count > 0 ? "assets_and_prefs" : "assets";
            var touched = new List<string>(created);
            touched.AddRange(changed);
            touched.AddRange(prefs);
            touched.Sort(StringComparer.Ordinal);
            var target = touched.Count == 0 ? "none" : string.Join(",", touched);
            if (target.Length > 160)
            {
                target = target.Substring(0, 157) + "...";
            }

            var existing = changed.Count + prefs.Count;
            return Create(unit, target, existing, existing + created.Count, created.Count, 0, existing);
        }

        public string AttachTo(string payloadJson)
        {
            var delta = JsonUtility.ToJson(this);
            var body = (payloadJson ?? "").Trim();
            if (body.Length < 2 || body[0] != '{' || body[body.Length - 1] != '}')
            {
                return "{\"mutation_delta\":" + delta + "}";
            }

            var inner = body.Substring(1, body.Length - 2).Trim();
            return inner.Length == 0
                ? "{\"mutation_delta\":" + delta + "}"
                : "{" + inner + ",\"mutation_delta\":" + delta + "}";
        }

        static HashSet<string> Distinct(IEnumerable<string> values)
        {
            var result = new HashSet<string>(StringComparer.Ordinal);
            foreach (var value in values ?? Array.Empty<string>())
            {
                if (!string.IsNullOrWhiteSpace(value))
                {
                    result.Add(value.Trim().Replace('\\', '/'));
                }
            }

            return result;
        }

        public static XUUnityLightMcpMutationDelta Create(
            string unit,
            string target,
            int beforeCount,
            int afterCount,
            int addedCount,
            int removedCount,
            int changedCount)
        {
            if (string.IsNullOrWhiteSpace(unit))
            {
                throw new ArgumentException("Mutation delta unit is required.", nameof(unit));
            }

            if (string.IsNullOrWhiteSpace(target))
            {
                throw new ArgumentException("Mutation delta target is required.", nameof(target));
            }

            if (beforeCount < 0 || afterCount < 0 || addedCount < 0 || removedCount < 0 || changedCount < 0)
            {
                throw new ArgumentOutOfRangeException(nameof(beforeCount), "Mutation delta counts cannot be negative.");
            }

            if (afterCount != beforeCount + addedCount - removedCount)
            {
                throw new ArgumentException(
                    "Mutation delta counts must satisfy afterCount = beforeCount + addedCount - removedCount.");
            }

            return new XUUnityLightMcpMutationDelta
            {
                unit = unit.Trim(),
                target = target.Trim(),
                before_count = beforeCount,
                after_count = afterCount,
                added_count = addedCount,
                removed_count = removedCount,
                changed_count = changedCount
            };
        }
    }
}
