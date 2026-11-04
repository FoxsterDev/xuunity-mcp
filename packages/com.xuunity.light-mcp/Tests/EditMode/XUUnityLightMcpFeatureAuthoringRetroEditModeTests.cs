using NUnit.Framework;
using UnityEngine;
using XUUnity.LightMcp.Editor.Bridge;
using XUUnity.LightMcp.Editor.ScenarioHooks;

namespace XUUnity.LightMcp.Tests.EditMode
{
    [Category("XUUnity.MCP.SelfTest")]
    [Category("XUUnity.MCP.EditMode")]
    [Category("XUUnity.MCP.Fast")]
    public sealed class XUUnityLightMcpFeatureAuthoringRetroEditModeTests
    {
        [Test]
        public void WrittenAssetsBecomeAValidDeltaInOneCall()
        {
            var delta = XUUnityLightMcpMutationDelta.FromWrittenAssets(
                new[] { "Assets/UI/A.prefab", "Assets/UI/B.prefab", "Assets\\UI\\A.prefab" },
                new[] { "Assets/UI/B.prefab" },
                new[] { "Feature.Debug.Force" });

            Assert.That(delta.schema_version, Is.EqualTo("xuunity.mutation-delta.v1"));
            Assert.That(delta.unit, Is.EqualTo("assets_and_prefs"));
            Assert.That(delta.added_count, Is.EqualTo(1));
            Assert.That(delta.changed_count, Is.EqualTo(2));
            Assert.That(delta.removed_count, Is.Zero);
            Assert.That(delta.after_count, Is.EqualTo(delta.before_count + delta.added_count - delta.removed_count));
            Assert.That(delta.target, Does.Contain("Assets/UI/A.prefab"));
        }

        [Test]
        public void AttachToAddsTheDeltaToAnExistingPayloadObject()
        {
            var delta = XUUnityLightMcpMutationDelta.FromWrittenAssets(new[] { "Assets/X.prefab" });

            var merged = delta.AttachTo("{\"built\":3}");
            var empty = delta.AttachTo("");

            Assert.That(merged, Does.StartWith("{\"built\":3,\"mutation_delta\":{"));
            Assert.That(empty, Does.StartWith("{\"mutation_delta\":{"));
            Assert.That(JsonUtility.FromJson<Holder>(merged).mutation_delta.unit, Is.EqualTo("assets"));
        }

        [Test]
        public void UnfocusedThrottleNamesTheBackgroundExecutionSwitchUntilItIsManaged()
        {
            Assert.That(
                XUUnityLightMcpPlayModeLivenessTracker.ResolveRemediation("playmode_throttled_editor_unfocused", false),
                Is.EqualTo(XUUnityLightMcpPlayModeLivenessTracker.BackgroundExecutionRemediation));
            Assert.That(
                XUUnityLightMcpPlayModeLivenessTracker.ResolveRemediation("playmode_throttled_editor_unfocused", true),
                Is.EqualTo(XUUnityLightMcpPlayModeLivenessTracker.ThrottledRemediation));
            Assert.That(
                XUUnityLightMcpPlayModeLivenessTracker.ResolveRemediation("playmode_throttled", false),
                Is.EqualTo(XUUnityLightMcpPlayModeLivenessTracker.ThrottledRemediation));
        }

        [System.Serializable]
        sealed class Holder
        {
            public XUUnityLightMcpMutationDelta mutation_delta;
        }
    }
}
