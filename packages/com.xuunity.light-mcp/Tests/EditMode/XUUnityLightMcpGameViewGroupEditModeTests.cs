using System;
using System.Reflection;
using NUnit.Framework;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;

namespace XUUnity.LightMcp.Tests.EditMode
{
    [Category("XUUnity.MCP.SelfTest")]
    [Category("XUUnity.MCP.EditMode")]
    [Category("XUUnity.MCP.Fast")]
    public sealed class XUUnityLightMcpGameViewGroupEditModeTests
    {
        static Type RequireGroupEnumType()
        {
            var groupEnumType = Type.GetType("UnityEditor.GameViewSizeGroupType,UnityEditor");
            Assert.IsNotNull(groupEnumType, "UnityEditor.GameViewSizeGroupType is not available in this editor version.");
            return groupEnumType;
        }

        [Test]
        public void ProbeResolvesTheActiveGroupForTheCurrentBuildTarget()
        {
            var probe = XUUnityLightMcpGameViewUtility.ProbeReflectionSurface();

            Assert.IsTrue(
                probe.supported,
                $"Game View reflection probe failed for the active build target: {probe.reason}");
        }

        [Test]
        public void UnityConverterFallbackResolvesTheActiveGroupOnThisEditor()
        {
            var converted = XUUnityLightMcpGameViewUtility.ConvertActiveBuildTargetToGroupType(out var reason);

            Assert.IsNotNull(
                converted,
                $"Unity's own BuildTargetGroupToGameViewSizeGroup must stay callable as the resolver fallback: {reason}");
            Assert.That(reason, Is.Empty);
            Assert.IsTrue(
                RequireGroupEnumType().IsInstanceOfType(converted),
                "the fallback must return a GameViewSizeGroupType value");
        }

        [Test]
        public void GroupNameMatchAcceptsTheLegacyIosAliasAndRejectsForeignGroups()
        {
            Assert.IsTrue(XUUnityLightMcpGameViewUtility.GroupNameMatches("iPhone", "iOS"));
            Assert.IsTrue(XUUnityLightMcpGameViewUtility.GroupNameMatches("iOS", "iPhone"));
            Assert.IsTrue(XUUnityLightMcpGameViewUtility.GroupNameMatches("android", "Android"));
            Assert.IsFalse(XUUnityLightMcpGameViewUtility.GroupNameMatches("Android", "iOS"));
            Assert.IsFalse(XUUnityLightMcpGameViewUtility.GroupNameMatches("iPhone", "Standalone"));
        }

        [Test]
        public void DescribeGroupTypeReportsTheUnityEnumMemberName()
        {
            var groupEnumType = RequireGroupEnumType();

            foreach (var name in Enum.GetNames(groupEnumType))
            {
                var value = Enum.Parse(groupEnumType, name);
                Assert.AreEqual(name, XUUnityLightMcpGameViewUtility.DescribeGroupType(value));
            }
        }

        [Test]
        public void FixedResolutionIsAGameViewSizeTypeMemberOnThisEditor()
        {
            var sizeTypeEnum = Type.GetType("UnityEditor.GameViewSizeType,UnityEditor");
            Assert.IsNotNull(sizeTypeEnum, "UnityEditor.GameViewSizeType is not available in this editor version.");

            Assert.Contains(
                XUUnityLightMcpGameViewUtility.FixedResolutionSizeTypeName,
                Enum.GetNames(sizeTypeEnum),
                "custom Game View size creation parses this member name, so it must exist");
        }

        [Test]
        public void AspectRatioIsAGameViewSizeTypeMemberOnThisEditor()
        {
            var sizeTypeEnum = Type.GetType("UnityEditor.GameViewSizeType,UnityEditor");
            Assert.IsNotNull(sizeTypeEnum, "UnityEditor.GameViewSizeType is not available in this editor version.");

            Assert.Contains(
                XUUnityLightMcpGameViewUtility.AspectRatioSizeTypeName,
                Enum.GetNames(sizeTypeEnum),
                "test environment capture classifies presets by this member name, so it must exist");
        }

        [Test]
        public void GameViewSizeExposesASizeTypePropertyOnThisEditor()
        {
            var sizeTypeEnum = Type.GetType("UnityEditor.GameViewSizeType,UnityEditor");
            Assert.IsNotNull(sizeTypeEnum, "UnityEditor.GameViewSizeType is not available in this editor version.");
            var sizeType = Type.GetType("UnityEditor.GameViewSize,UnityEditor");
            Assert.IsNotNull(sizeType, "UnityEditor.GameViewSize is not available in this editor version.");

            var property = sizeType.GetProperty("sizeType", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);

            Assert.IsNotNull(property, "configure matches fixed resolutions by reading GameViewSize.sizeType, so it must exist");
            Assert.AreEqual(sizeTypeEnum, property.PropertyType);
        }

        [Test]
        public void CaptureTestEnvironmentNeverThrowsAndReportsAKnownStatus()
        {
            XUUnityLightMcpTestEnvironment environment = null;
            Assert.DoesNotThrow(() => environment = XUUnityLightMcpGameViewUtility.CaptureTestEnvironment());

            Assert.IsNotNull(environment);
            Assert.AreEqual("request_start", environment.captured_at);
            Assert.Contains(
                environment.capture_status,
                new[]
                {
                    XUUnityLightMcpGameViewUtility.CaptureStatusCaptured,
                    XUUnityLightMcpGameViewUtility.CaptureStatusNotRendered,
                    XUUnityLightMcpGameViewUtility.CaptureStatusNoGameView,
                    XUUnityLightMcpGameViewUtility.CaptureStatusUnavailable
                });
            Assert.IsNotEmpty(environment.build_target);
            if (environment.capture_status == XUUnityLightMcpGameViewUtility.CaptureStatusCaptured)
            {
                Assert.Greater(environment.render_width, 0);
                Assert.Greater(environment.render_height, 0);
            }
            else
            {
                Assert.AreEqual(0, environment.render_width);
                Assert.AreEqual(0, environment.render_height);
                Assert.IsEmpty(environment.render_matches_preset);
            }

            if (environment.preset_kind != XUUnityLightMcpGameViewUtility.PresetKindFixedResolution)
            {
                Assert.AreEqual(0, environment.preset_width);
                Assert.AreEqual(0, environment.preset_height);
                Assert.IsEmpty(environment.render_matches_preset);
            }

            Assert.LessOrEqual(environment.preset_label.Length, XUUnityLightMcpGameViewUtility.TestEnvironmentTextLimit);
        }

        [TestCase("FixedResolution", 1080, 1920, "fixed_resolution", 1080, 1920)]
        [TestCase("AspectRatio", 9, 16, "aspect_ratio", 0, 0)]
        [TestCase("AspectRatio", 0, 0, "free", 0, 0)]
        [TestCase("FixedResolution", 0, 0, "unknown", 0, 0)]
        [TestCase("", 1080, 1920, "unknown", 0, 0)]
        public void PresetPixelFieldsStayZeroUnlessTheKindIsFixedResolution(
            string sizeTypeName,
            int width,
            int height,
            string expectedKind,
            int expectedWidth,
            int expectedHeight)
        {
            var environment = new XUUnityLightMcpTestEnvironment
            {
                capture_status = XUUnityLightMcpGameViewUtility.CaptureStatusNotRendered
            };

            XUUnityLightMcpGameViewUtility.ApplyPresetToTestEnvironment(environment, "Preset", sizeTypeName, width, height);

            Assert.AreEqual(expectedKind, environment.preset_kind);
            Assert.AreEqual(expectedWidth, environment.preset_width);
            Assert.AreEqual(expectedHeight, environment.preset_height);
            Assert.IsEmpty(environment.render_matches_preset);
        }

        [TestCase("FixedResolution", 1440, 3200, 1440, 3200, "true")]
        [TestCase("FixedResolution", 1080, 1920, 1440, 3200, "false")]
        [TestCase("AspectRatio", 9, 16, 1440, 3200, "")]
        [TestCase("AspectRatio", 0, 0, 1440, 3200, "")]
        public void RenderMatchesPresetIsOnlyComparedForRenderedFixedResolutions(
            string sizeTypeName,
            int presetWidth,
            int presetHeight,
            int renderWidth,
            int renderHeight,
            string expected)
        {
            var environment = new XUUnityLightMcpTestEnvironment
            {
                capture_status = XUUnityLightMcpGameViewUtility.CaptureStatusCaptured,
                render_width = renderWidth,
                render_height = renderHeight
            };

            XUUnityLightMcpGameViewUtility.ApplyPresetToTestEnvironment(
                environment,
                "Preset",
                sizeTypeName,
                presetWidth,
                presetHeight);

            Assert.AreEqual(expected, environment.render_matches_preset);
        }

        [TestCase("FixedResolution", 9, 16, 9, 16, true, false)]
        [TestCase("FixedResolution", 1440, 3200, 1440, 3200, true, false)]
        [TestCase("AspectRatio", 9, 16, 9, 16, false, true)]
        [TestCase("AspectRatio", 16, 9, 9, 16, false, false)]
        [TestCase("FixedResolution", 16, 9, 9, 16, false, false)]
        [TestCase("AspectRatio", 0, 0, 0, 0, false, false)]
        [TestCase("", 9, 16, 9, 16, false, false)]
        public void ConfigureOnlyMatchesFixedResolutionSizes(
            string sizeTypeName,
            int width,
            int height,
            int targetWidth,
            int targetHeight,
            bool expectedFixedMatch,
            bool expectedAspectRatioShapeMatch)
        {
            Assert.AreEqual(
                expectedFixedMatch,
                XUUnityLightMcpGameViewUtility.IsFixedResolutionMatch(sizeTypeName, width, height, targetWidth, targetHeight));
            Assert.AreEqual(
                expectedAspectRatioShapeMatch,
                XUUnityLightMcpGameViewUtility.IsAspectRatioShapeMatch(sizeTypeName, width, height, targetWidth, targetHeight));
        }

        [Test]
        public void MissingFixedResolutionNamesAnAspectRatioPresetOfTheSameShape()
        {
            var withPreset = XUUnityLightMcpGameViewUtility.DescribeMissingFixedResolution(9, 16, "Android", "16:9 Portrait");
            StringAssert.Contains("9x16", withPreset);
            StringAssert.Contains("'16:9 Portrait'", withPreset);
            StringAssert.Contains("is not a fixed resolution", withPreset);
            StringAssert.Contains("allowCreateCustomSize=true", withPreset);

            var unlabeled = XUUnityLightMcpGameViewUtility.DescribeMissingFixedResolution(9, 16, "Android", "");
            StringAssert.Contains("is not a fixed resolution", unlabeled);
            StringAssert.DoesNotContain("''", unlabeled);

            var withoutPreset = XUUnityLightMcpGameViewUtility.DescribeMissingFixedResolution(1440, 3200, "Android", null);
            StringAssert.DoesNotContain("aspect-ratio", withoutPreset);
            StringAssert.Contains("allowCreateCustomSize=true", withoutPreset);
        }

        [Test]
        public void TestEnvironmentTextIsBoundedWithoutSplittingASurrogatePair()
        {
            var limit = XUUnityLightMcpGameViewUtility.TestEnvironmentTextLimit;
            Assert.AreEqual(limit, XUUnityLightMcpGameViewUtility.BoundTestEnvironmentText(new string('L', 500)).Length);

            var pairAtBoundary = new string('a', limit - 1) + "😀tail";
            var bounded = XUUnityLightMcpGameViewUtility.BoundTestEnvironmentText(pairAtBoundary);
            Assert.AreEqual(limit - 1, bounded.Length);
            Assert.IsFalse(char.IsHighSurrogate(bounded[bounded.Length - 1]));
            Assert.AreEqual("", XUUnityLightMcpGameViewUtility.BoundTestEnvironmentText(null));
        }
    }
}
