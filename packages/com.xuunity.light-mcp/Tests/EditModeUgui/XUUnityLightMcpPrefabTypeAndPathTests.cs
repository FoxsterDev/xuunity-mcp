using System.Collections.Generic;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.UI;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;

namespace XUUnity.LightMcp.Tests.EditModeUgui
{
    [Category("XUUnity.MCP.SelfTest")]
    [Category("XUUnity.MCP.EditMode")]
    [Category("XUUnity.MCP.Fast")]
    [Category("XUUnity.MCP.PrefabMutation")]
    public sealed class XUUnityLightMcpPrefabTypeAndPathTests
    {
        const string ROOT = "XUUnityMcp_TypeRoot";

        GameObject _root;

        [SetUp]
        public void SetUp()
        {
            _root = new GameObject(ROOT, typeof(RectTransform));
            var panel = new GameObject("Panel", typeof(RectTransform), typeof(Image));
            panel.transform.SetParent(_root.transform, false);
        }

        [TearDown]
        public void TearDown()
        {
            Object.DestroyImmediate(_root);
        }

        [TestCase("UnityEngine.UI.Image")]
        [TestCase("UnityEngine.UI.Image, UnityEngine.UI")]
        [TestCase("Image")]
        public void AddComponentResolvesFullAssemblyQualifiedAndUniqueShortNames(string componentType)
        {
            RequireUniqueShortName("Image");
            var change = Apply("add_component", ROOT, componentType, AllowAny);

            Assert.That(change.status, Is.EqualTo("applied"), change.error_message);
            Assert.That(change.after, Is.EqualTo("added:UnityEngine.UI.Image"));
            Assert.That(_root.GetComponent<Image>(), Is.Not.Null);
        }

        [Test]
        public void AnAmbiguousShortNameIsRefusedWithItsCandidates()
        {
            var change = Apply("add_component", ROOT, "XUUnityMcpRg48AmbiguousProbe", AllowAny);

            Assert.That(change.status, Is.EqualTo("failed"));
            Assert.That(change.error_code, Is.EqualTo("prefab_mutation_component_type_ambiguous"));
            StringAssert.Contains("XUUnity.LightMcp.Tests.EditModeUgui.Rg48First.XUUnityMcpRg48AmbiguousProbe", change.error_message);
            StringAssert.Contains("XUUnity.LightMcp.Tests.EditModeUgui.Rg48Second.XUUnityMcpRg48AmbiguousProbe", change.error_message);
        }

        [Test]
        public void TheAllowlistMatchesByFullNameAndByShortName()
        {
            RequireUniqueShortName("Image");
            var byFullName = new HashSet<string> { "UnityEngine.UI.Image" };
            Assert.That(Apply("add_component", ROOT, "Image", byFullName).status, Is.EqualTo("applied"));
            Object.DestroyImmediate(_root.GetComponent<Image>());

            var byShortName = new HashSet<string> { "Image" };
            Assert.That(Apply("add_component", ROOT, "UnityEngine.UI.Image", byShortName).status, Is.EqualTo("applied"));

            var removal = Apply("remove_component", ROOT + "/Panel", "UnityEngine.UI.Image", byShortName);
            Assert.That(removal.status, Is.EqualTo("applied"), removal.error_message);

            var refused = Apply("add_component", ROOT, "UnityEngine.UI.Outline", byFullName);
            Assert.That(refused.error_code, Is.EqualTo("prefab_mutation_component_not_allowlisted"));
        }

        [Test]
        public void ComponentLookupOnTheTargetAcceptsTheFullName()
        {
            var operation = Operation("set_serialized_field", ROOT + "/Panel", "UnityEngine.UI.Image");
            operation.propertyPath = "m_RaycastTarget";
            operation.boolValue = false;

            var change = XUUnityLightMcpPrefabMutator.Apply(_root, operation, 0, AllowAny);

            Assert.That(change.status, Is.EqualTo("applied"), change.error_message);
            Assert.That(_root.transform.Find("Panel").GetComponent<Image>().raycastTarget, Is.False);
        }

        [Test]
        public void TheReferenceTypeChainAcceptsShortAndFullNames()
        {
            Assert.That(XUUnityLightMcpPrefabInspector.TypeChainContains(typeof(Image), "Graphic"), Is.True);
            Assert.That(XUUnityLightMcpPrefabInspector.TypeChainContains(typeof(Image), "UnityEngine.UI.Graphic"), Is.True);
            Assert.That(XUUnityLightMcpPrefabInspector.TypeChainContains(typeof(Image), "UnityEngine.UI.Button"), Is.False);
        }

        [Test]
        public void ARootlessPathResolvesWhenItIsUnique()
        {
            var operation = Operation("set_active", "Panel", "");
            operation.boolValue = false;

            var change = XUUnityLightMcpPrefabMutator.Apply(_root, operation, 0, AllowAny);

            Assert.That(change.status, Is.EqualTo("applied"), change.error_message);
            Assert.That(_root.transform.Find("Panel").gameObject.activeSelf, Is.False);
        }

        [Test]
        public void AnAmbiguousRootlessPathIsRefused()
        {
            for (var index = 0; index < 2; index++)
            {
                new GameObject("Dup", typeof(RectTransform)).transform.SetParent(_root.transform, false);
            }

            var resolved = XUUnityLightMcpPrefabMutator.TryResolveUnique(_root, "Dup", out _, out var code, out _);

            Assert.That(resolved, Is.False);
            Assert.That(code, Is.EqualTo("prefab_mutation_target_ambiguous"));
        }

        [Test]
        public void AMissNamesTheRootAndTheNearestSuffixMatches()
        {
            var resolved = XUUnityLightMcpPrefabMutator.TryResolveUnique(_root, "Wrong/Panel", out _, out var code, out var message);

            Assert.That(resolved, Is.False);
            Assert.That(code, Is.EqualTo("prefab_mutation_target_not_found"));
            StringAssert.Contains($"root '{ROOT}'", message);
            StringAssert.Contains($"nearest matches: {ROOT}/Panel", message);
        }

        static readonly HashSet<string> AllowAny = new();

        static void RequireUniqueShortName(string shortName)
        {
            if (XUUnityLightMcpTypeNameMatcher.ResolveComponentType(shortName, out _) == null)
            {
                Assert.Ignore($"This project has more than one component type named '{shortName}'.");
            }
        }

        XUUnityLightMcpPrefabMutationChange Apply(string op, string path, string componentType, HashSet<string> allowed)
        {
            return XUUnityLightMcpPrefabMutator.Apply(
                _root,
                Operation(op, path, componentType),
                0,
                allowed,
                ReferenceEquals(allowed, AllowAny));
        }

        static XUUnityLightMcpPrefabMutationOperation Operation(string op, string path, string componentType)
        {
            return new XUUnityLightMcpPrefabMutationOperation { op = op, path = path, componentType = componentType };
        }
    }
}

namespace XUUnity.LightMcp.Tests.EditModeUgui.Rg48First
{
    public sealed class XUUnityMcpRg48AmbiguousProbe : MonoBehaviour
    {
    }
}

namespace XUUnity.LightMcp.Tests.EditModeUgui.Rg48Second
{
    public sealed class XUUnityMcpRg48AmbiguousProbe : MonoBehaviour
    {
    }
}
