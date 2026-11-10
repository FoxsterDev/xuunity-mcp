using System;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;

namespace XUUnity.LightMcp.Editor.Helpers
{
    internal static class XUUnityLightMcpTypeNameMatcher
    {
        public static bool Matches(Type type, string name)
        {
            if (type == null || string.IsNullOrWhiteSpace(name))
            {
                return false;
            }

            var wanted = name.Trim();
            return string.Equals(type.Name, wanted, StringComparison.Ordinal) || MatchesQualified(type, wanted);
        }

        public static bool MatchesQualified(Type type, string wanted)
        {
            return string.Equals(type.FullName, wanted, StringComparison.Ordinal)
                   || string.Equals(type.AssemblyQualifiedName, wanted, StringComparison.Ordinal)
                   || string.Equals(ShortAssemblyQualifiedName(type), wanted, StringComparison.Ordinal);
        }

        public static string ShortAssemblyQualifiedName(Type type)
        {
            return type.FullName + ", " + type.Assembly.GetName().Name;
        }

        public static Type ResolveComponentType(string name, out List<string> ambiguousCandidates)
        {
            ambiguousCandidates = new List<string>();
            var wanted = (name ?? "").Trim();
            if (wanted.Length == 0)
            {
                return null;
            }

            var qualified = new List<Type>();
            var shortNamed = new List<Type>();
            foreach (var candidate in TypeCache.GetTypesDerivedFrom<Component>())
            {
                if (MatchesQualified(candidate, wanted))
                {
                    qualified.Add(candidate);
                }
                else if (string.Equals(candidate.Name, wanted, StringComparison.Ordinal))
                {
                    shortNamed.Add(candidate);
                }
            }

            var matches = qualified.Count > 0 ? qualified : shortNamed;
            if (matches.Count == 1)
            {
                return matches[0];
            }

            foreach (var match in matches)
            {
                ambiguousCandidates.Add(qualified.Count > 0 ? ShortAssemblyQualifiedName(match) : match.FullName);
            }

            ambiguousCandidates.Sort(StringComparer.Ordinal);
            return null;
        }

        public static bool AllowlistAccepts(ICollection<string> allowlist, string requestedName, Type type)
        {
            if (allowlist.Contains((requestedName ?? "").Trim()))
            {
                return true;
            }

            if (type == null)
            {
                return false;
            }

            foreach (var entry in allowlist)
            {
                if (Matches(type, entry))
                {
                    return true;
                }
            }

            return false;
        }
    }
}
