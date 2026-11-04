using System;
using UnityEditor;
using UnityEditorInternal;
using UnityEngine;

namespace XUUnity.LightMcp.Editor.Bridge
{
    internal static class XUUnityLightMcpPlayModeLivenessTracker
    {
        public const string ThrottledUnfocusedWarning = "playmode_throttled_editor_unfocused";
        public const string ThrottledFocusedWarning = "playmode_throttled";
        public const string UnprovenUnfocusedWarning = "playmode_liveness_unproven_editor_unfocused";
        public const string ThrottledRemediation = "focus_the_unity_editor_or_set_interaction_mode_to_no_throttling";
        public const string UnprovenRemediation = "wait_for_playmode_liveness_sample_and_retry";
        public const string BackgroundExecutionRemediation =
            "enable_background_execution_with_unity_playmode_set_background_execution_managed_or_focus_the_unity_editor";

        const double MIN_SAMPLE_INTERVAL_SECONDS = 1.0d;
        const int ADVANCING_FRAME_THRESHOLD = 2;

        static bool _hasBaselineSample;
        static bool _baselineWasPlaying;
        static int _baselineFrameCount;
        static double _baselineSampleEditorTime;
        static bool _hasIntervalEvidence;
        static int _framesAdvancedLastInterval;
        static double _sampleIntervalSeconds;

        public static int FramesAdvancedLastInterval => _framesAdvancedLastInterval;
        public static double SampleIntervalSeconds => _sampleIntervalSeconds;
        public static bool HasIntervalEvidence => _hasIntervalEvidence;
        public static int CurrentFrameCount => Time.frameCount;
        public static bool EditorApplicationFocused => InternalEditorUtility.isApplicationActive;

        public static void Sample()
        {
            var frameCount = Time.frameCount;
            var now = EditorApplication.timeSinceStartup;
            var isPlaying = EditorApplication.isPlaying;

            if (!_hasBaselineSample || isPlaying != _baselineWasPlaying)
            {
                ResetBaseline(frameCount, now, isPlaying);
                return;
            }

            var interval = now - _baselineSampleEditorTime;
            if (interval < MIN_SAMPLE_INTERVAL_SECONDS)
            {
                return;
            }

            _framesAdvancedLastInterval = Math.Max(0, frameCount - _baselineFrameCount);
            _sampleIntervalSeconds = interval;
            _hasIntervalEvidence = true;
            _baselineFrameCount = frameCount;
            _baselineSampleEditorTime = now;
        }

        public static string ResolveCurrentLiveness(string playmodeState)
        {
            return ResolveLiveness(playmodeState, _hasIntervalEvidence, _framesAdvancedLastInterval);
        }

        internal static string ResolveLiveness(string playmodeState, bool hasIntervalEvidence, int framesAdvancedLastInterval)
        {
            switch (playmodeState)
            {
                case "playing":
                    if (!hasIntervalEvidence)
                    {
                        return "unknown";
                    }

                    return framesAdvancedLastInterval < ADVANCING_FRAME_THRESHOLD ? "throttled" : "advancing";
                case "paused":
                    return "paused";
                default:
                    return "not_playing";
            }
        }

        internal static string ResolveWarning(string liveness, bool editorApplicationFocused)
        {
            if (liveness == "unknown" && !editorApplicationFocused)
            {
                return UnprovenUnfocusedWarning;
            }

            if (liveness != "throttled")
            {
                return "";
            }

            return editorApplicationFocused ? ThrottledFocusedWarning : ThrottledUnfocusedWarning;
        }

        internal static string ResolveRemediation(string warning)
        {
            return ResolveRemediation(
                warning,
                XUUnityLightMcpBackgroundExecution.Mode == XUUnityLightMcpBackgroundExecution.ManagedMode);
        }

        internal static string ResolveRemediation(string warning, bool backgroundExecutionManaged)
        {
            if (string.IsNullOrEmpty(warning))
            {
                return "";
            }

            if (warning == UnprovenUnfocusedWarning)
            {
                return UnprovenRemediation;
            }

            return warning == ThrottledUnfocusedWarning && !backgroundExecutionManaged
                ? BackgroundExecutionRemediation
                : ThrottledRemediation;
        }

        static void ResetBaseline(int frameCount, double now, bool isPlaying)
        {
            _hasBaselineSample = true;
            _baselineWasPlaying = isPlaying;
            _baselineFrameCount = frameCount;
            _baselineSampleEditorTime = now;
            _hasIntervalEvidence = false;
            _framesAdvancedLastInterval = 0;
            _sampleIntervalSeconds = 0d;
        }
    }
}
