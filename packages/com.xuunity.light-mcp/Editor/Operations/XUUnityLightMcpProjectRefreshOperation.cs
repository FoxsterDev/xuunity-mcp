using System;
using UnityEditor;
using UnityEditor.Compilation;
using UnityEditor.PackageManager;
using UnityEngine;
using XUUnity.LightMcp.Editor.Bridge;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;

namespace XUUnity.LightMcp.Editor.Operations
{
    internal sealed class XUUnityLightMcpProjectRefreshOperation : IXUUnityLightMcpOperation
    {
        public string OperationName => "unity.project.refresh";

        public XUUnityLightMcpResponse Execute(XUUnityLightMcpRequest request)
        {
            var args = string.IsNullOrWhiteSpace(request.args_json)
                ? new XUUnityLightMcpProjectRefreshArgs()
                : JsonUtility.FromJson<XUUnityLightMcpProjectRefreshArgs>(request.args_json) ?? new XUUnityLightMcpProjectRefreshArgs();

            try
            {
                var requestCompletedAtUtc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");
                XUUnityLightMcpBridgeRuntimeState.BeginRefreshSettleTracking(request.request_id, args.resolvePackages, args.forceAssetRefresh);
                XUUnityLightMcpLifecycleMonitor.MarkAssetRefreshRequested();
                if (args.forceAssetRefresh)
                {
                    AssetDatabase.Refresh(ImportAssetOptions.ForceUpdate);
                }
                else
                {
                    AssetDatabase.Refresh();
                }

                if (args.resolvePackages)
                {
                    XUUnityLightMcpLifecycleMonitor.MarkPackageResolveRequested();
                    Client.Resolve();
                }

                if (args.rerunHealthProbe)
                {
                    XUUnityLightMcpHealthProbe.RunProbeAndPersist();
                }

                var compileRequestReason = "";
                var content = XUUnityLightMcpEditorInputSnapshot.Compare(XUUnityLightMcpFileIpcPaths.ProjectRootPath);
                if (content.ContentChanged && !EditorApplication.isCompiling && !EditorApplication.isPlayingOrWillChangePlaymode)
                {
                    CompilationPipeline.RequestScriptCompilation();
                    compileRequestReason = "editor_input_content_changed_without_compile";
                }

                var payload = new XUUnityLightMcpProjectRefreshPayload
                {
                    project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                    outcome = args.resolvePackages ? "refresh_and_resolve_requested" : "refresh_requested",
                    request_completed_at_utc = requestCompletedAtUtc,
                    asset_database_refreshed = true,
                    package_resolve_requested = args.resolvePackages,
                    capabilities_report_refreshed = args.rerunHealthProbe,
                    editor_is_compiling_after_request = EditorApplication.isCompiling,
                    editor_is_updating_after_request = EditorApplication.isUpdating,
                    playmode_state_after_request = XUUnityLightMcpPlayModeStateOperation.ResolvePlayModeState(),
                    settle_request_id = request.request_id,
                    settle_phase = XUUnityLightMcpBridgeRuntimeState.RefreshSettlePhase,
                    script_compilation_requested = compileRequestReason.Length > 0,
                    script_compilation_request_reason = compileRequestReason,
                    changed_editor_input_count = content.changed_count,
                    changed_editor_inputs = content.changed_paths.ToArray(),
                };

                return XUUnityLightMcpResponseWriter.Success(
                    request.request_id,
                    OperationName,
                    JsonUtility.ToJson(payload)
                );
            }
            catch (Exception ex)
            {
                return XUUnityLightMcpResponseWriter.Error(request.request_id, "project_refresh_failed", ex.Message);
            }
        }
    }
}
