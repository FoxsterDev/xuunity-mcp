using System;
using UnityEditor;
using UnityEngine;
using XUUnity.LightMcp.Editor.Helpers;
using XUUnity.LightMcp.Editor.Operations;

namespace XUUnity.LightMcp.Editor.Bridge
{
    internal static class XUUnityLightMcpBridgeProcessIdentity
    {
        internal const string MainEditorProcessClass = "main_editor";
        internal const string ImportWorkerProcessClass = "import_worker";
        internal const string BatchProcessClass = "batch";

        internal static bool CommandLineLooksLikeImportWorker(string[] arguments)
        {
            if (arguments == null)
            {
                return false;
            }

            for (var index = 0; index < arguments.Length; index += 1)
            {
                var argument = arguments[index] ?? "";
                if (string.Equals(argument, "-assetImportWorker", StringComparison.OrdinalIgnoreCase))
                {
                    return true;
                }

                if (
                    string.Equals(argument, "-name", StringComparison.OrdinalIgnoreCase)
                    && index + 1 < arguments.Length
                    && (arguments[index + 1] ?? "").StartsWith("AssetImportWorker", StringComparison.OrdinalIgnoreCase)
                )
                {
                    return true;
                }
            }

            return false;
        }

        internal static string ClassifyProcess(string[] arguments, bool assetDatabaseReportsImportWorker, bool isBatchMode)
        {
            if (assetDatabaseReportsImportWorker || CommandLineLooksLikeImportWorker(arguments))
            {
                return ImportWorkerProcessClass;
            }

            return isBatchMode ? BatchProcessClass : MainEditorProcessClass;
        }

        internal static string ResolveCurrentProcessClass()
        {
            var isImportWorker = false;
            try
            {
                isImportWorker = AssetDatabase.IsAssetImportWorkerProcess();
            }
            catch
            {
            }

            return ClassifyProcess(Environment.GetCommandLineArgs(), isImportWorker, Application.isBatchMode);
        }
    }

    [InitializeOnLoad]
    internal static class XUUnityLightMcpBridgeBootstrap
    {
        static double _heartbeatIntervalSeconds = 2.0d;
        static double _pumpIntervalSeconds = 0.5d;
        static double _lastHeartbeatAt;
        static double _lastPumpAt;

        static XUUnityLightMcpBridgeBootstrap()
        {
            var processClass = XUUnityLightMcpBridgeProcessIdentity.ResolveCurrentProcessClass();
            if (processClass == XUUnityLightMcpBridgeProcessIdentity.ImportWorkerProcessClass)
            {
                return;
            }

            XUUnityLightMcpBridgeRuntimeState.StampEditorDomainLoaded();

            if (!XUUnityLightMcpBridgeActivation.IsEnabled())
            {
                XUUnityLightMcpBackgroundExecution.Restore();
                return;
            }

            var config = XUUnityLightMcpBridgeActivation.LoadConfig();
            _heartbeatIntervalSeconds = config.heartbeat_interval_ms / 1000.0d;
            _pumpIntervalSeconds = config.pump_interval_ms / 1000.0d;

            XUUnityLightMcpBackgroundExecution.ApplyIfConfigured();
            EditorApplication.quitting -= XUUnityLightMcpBackgroundExecution.Restore;
            EditorApplication.quitting += XUUnityLightMcpBackgroundExecution.Restore;
            XUUnityLightMcpBridgeRuntimeState.InitializeBridgeSession();
            XUUnityLightMcpBridgeTransportRuntime.Initialize(config);
            XUUnityLightMcpLifecycleMonitor.InitializeIfNeeded();
            XUUnityLightMcpRequestJournal.WriteBootstrapAttached(processClass);
            XUUnityLightMcpConsoleBuffer.EnsureStarted();
            if (config.auto_probe_on_startup)
            {
                try
                {
                    XUUnityLightMcpHealthProbe.EnsureCurrentReport();
                }
                catch
                {
                }
            }
            XUUnityLightMcpEditorQuitScheduler.RestoreFromSessionState();
            EditorApplication.update -= OnUpdate;
            EditorApplication.update += OnUpdate;
        }

        static void OnUpdate()
        {
            XUUnityLightMcpEditorQuitScheduler.Tick();
            var now = EditorApplication.timeSinceStartup;

            if (now - _lastHeartbeatAt >= _heartbeatIntervalSeconds)
            {
                try
                {
                    XUUnityLightMcpPlayModeLivenessTracker.Sample();
                    XUUnityLightMcpBridgeStateWriter.WriteHeartbeat();
                }
                catch (Exception ex)
                {
                    XUUnityLightMcpBridgeStateWriter.WriteHeartbeat(ex.Message);
                }
                _lastHeartbeatAt = now;
            }

            if (now - _lastPumpAt >= _pumpIntervalSeconds)
            {
                XUUnityLightMcpLifecycleMonitor.Tick();
                XUUnityLightMcpBridgeRequestPump.PumpOnce();
                XUUnityLightMcpSdkAndroidResolveRuntime.Tick();
                XUUnityLightMcpScenarioRunner.Tick();
                _lastPumpAt = now;
            }
        }
    }
}
