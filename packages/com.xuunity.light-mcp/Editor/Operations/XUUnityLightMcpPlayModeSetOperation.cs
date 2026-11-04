using System;
using UnityEditor;
using UnityEngine;
using XUUnity.LightMcp.Editor.Bridge;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;

namespace XUUnity.LightMcp.Editor.Operations
{
    internal sealed class XUUnityLightMcpPlayModeSetOperation : IXUUnityLightMcpOperation
    {
        public string OperationName => "unity.playmode.set";

        public XUUnityLightMcpResponse Execute(XUUnityLightMcpRequest request)
        {
            var args = string.IsNullOrWhiteSpace(request.args_json)
                ? new XUUnityLightMcpPlayModeSetArgs()
                : JsonUtility.FromJson<XUUnityLightMcpPlayModeSetArgs>(request.args_json) ?? new XUUnityLightMcpPlayModeSetArgs();

            var action = (args.action ?? "").Trim().ToLowerInvariant();
            if (string.IsNullOrWhiteSpace(action))
            {
                return XUUnityLightMcpResponseWriter.Error(request.request_id, "missing_action",
                    "unity.playmode.set requires action: enter, exit, pause, resume, or configure.");
            }

            var backgroundChange = "";
            var requestedBackground = (args.backgroundExecution ?? "").Trim().ToLowerInvariant();
            if (requestedBackground.Length > 0)
            {
                if (requestedBackground != XUUnityLightMcpBackgroundExecution.ManagedMode
                    && requestedBackground != XUUnityLightMcpBackgroundExecution.ProjectOwnedMode)
                {
                    return XUUnityLightMcpResponseWriter.Error(request.request_id, "invalid_args",
                        "backgroundExecution must be 'managed' or 'project_owned'.");
                }

                var before = XUUnityLightMcpBackgroundExecution.Mode;
                if (!XUUnityLightMcpBackgroundExecution.TrySetConfigured(
                        requestedBackground == XUUnityLightMcpBackgroundExecution.ManagedMode,
                        out var configError))
                {
                    return XUUnityLightMcpResponseWriter.Error(request.request_id, "bridge_config_write_failed", configError);
                }

                backgroundChange = before == requestedBackground ? "unchanged" : $"{before}->{requestedBackground}";
            }
            else if (action == "configure")
            {
                return XUUnityLightMcpResponseWriter.Error(request.request_id, "invalid_args",
                    "action 'configure' requires backgroundExecution: managed or project_owned.");
            }

            if (action == "configure")
            {
                var configured = new XUUnityLightMcpPlayModeSetPayload
                {
                    project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                    requested_action = action,
                    outcome = "configured",
                    request_completed_at_utc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                };
                FillBackgroundEvidence(configured, backgroundChange);
                var currentState = XUUnityLightMcpPlayModeStateOperation.BuildPayload();
                configured.is_playing = currentState.is_playing;
                configured.is_paused = currentState.is_paused;
                configured.playmode_state = currentState.playmode_state;
                XUUnityLightMcpPlayModeStateOperation.PopulateLivenessEvidence(configured, currentState.playmode_state);
                return XUUnityLightMcpResponseWriter.Success(request.request_id, OperationName, JsonUtility.ToJson(configured));
            }

            var targetState = ResolveTargetState(action);
            XUUnityLightMcpBridgeRuntimeState.BeginPlayModeTransitionTracking(request.request_id, action, targetState);
            string outcome;
            try
            {
                outcome = action switch
                {
                    "enter" => EnterPlayMode(),
                    "exit" => ExitPlayMode(),
                    "pause" => PausePlayMode(),
                    "resume" => ResumePlayMode(),
                    _ => throw new InvalidOperationException(
                        $"Unsupported play mode action '{action}'. Valid actions: enter, exit, pause, resume, configure.")
                };
            }
            catch (Exception ex)
            {
                XUUnityLightMcpBridgeRuntimeState.CancelPlayModeTransitionTracking();
                return XUUnityLightMcpResponseWriter.Error(request.request_id, "playmode_action_failed", ex.Message);
            }

            var requestCompletedAtUtc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");
            var state = XUUnityLightMcpPlayModeStateOperation.BuildPayload();
            var payload = new XUUnityLightMcpPlayModeSetPayload
            {
                project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                requested_action = action,
                outcome = outcome,
                request_completed_at_utc = requestCompletedAtUtc,
                settle_request_id = request.request_id,
                settle_phase = XUUnityLightMcpBridgeRuntimeState.PlayModeTransitionPhase,
                settle_target_state = targetState,
                is_playing = state.is_playing,
                is_paused = state.is_paused,
                is_playing_or_will_change_playmode = state.is_playing_or_will_change_playmode,
                playmode_state = state.playmode_state
            };
            XUUnityLightMcpPlayModeStateOperation.PopulateLivenessEvidence(payload, state.playmode_state);
            FillBackgroundEvidence(payload, backgroundChange);

            return XUUnityLightMcpResponseWriter.Success(
                request.request_id,
                OperationName,
                JsonUtility.ToJson(payload)
            );
        }

        static void FillBackgroundEvidence(XUUnityLightMcpPlayModeSetPayload payload, string change)
        {
            payload.background_execution_mode = XUUnityLightMcpBackgroundExecution.Mode;
            payload.background_execution_change = change;
            payload.application_run_in_background = Application.runInBackground;
        }

        static string EnterPlayMode()
        {
            if (EditorApplication.isPlaying)
            {
                return "already_playing";
            }

            if (EditorApplication.isPlayingOrWillChangePlaymode)
            {
                return "already_transitioning";
            }

            try
            {
                XUUnityLightMcpGameViewUtility.EnsureGameView();
            }
            catch
            {
            }

            EditorApplication.isPlaying = true;
            return "enter_requested";
        }

        static string ExitPlayMode()
        {
            if (!EditorApplication.isPlaying && !EditorApplication.isPlayingOrWillChangePlaymode)
            {
                return "already_in_edit_mode";
            }

            EditorApplication.isPlaying = false;
            return "exit_requested";
        }

        static string PausePlayMode()
        {
            if (!EditorApplication.isPlaying)
            {
                throw new InvalidOperationException("Cannot pause because Unity is not currently in play mode.");
            }

            if (EditorApplication.isPaused)
            {
                return "already_paused";
            }

            EditorApplication.isPaused = true;
            return "pause_requested";
        }

        static string ResumePlayMode()
        {
            if (!EditorApplication.isPlaying)
            {
                throw new InvalidOperationException("Cannot resume because Unity is not currently in play mode.");
            }

            if (!EditorApplication.isPaused)
            {
                return "already_running";
            }

            EditorApplication.isPaused = false;
            return "resume_requested";
        }

        static string ResolveTargetState(string action)
        {
            return action switch
            {
                "enter" => "playing",
                "exit" => "edit",
                "pause" => "paused",
                "resume" => "playing",
                _ => ""
            };
        }
    }
}
