using System;
using System.Collections.Generic;
using XUUnity.LightMcp.Editor.Operations;

namespace XUUnity.LightMcp.Editor.Core
{
    internal interface IXUUnityLightMcpOperation
    {
        string OperationName { get; }
        XUUnityLightMcpResponse Execute(XUUnityLightMcpRequest request);
    }

    internal static class XUUnityLightMcpOperationRegistry
    {
        static readonly Dictionary<string, IXUUnityLightMcpOperation> Operations = new(StringComparer.Ordinal)
        {
            { "unity.status", new XUUnityLightMcpStatusOperation() },
            { "unity.capabilities.get", new XUUnityLightMcpCapabilitiesGetOperation() },
            { "unity.health.probe", new XUUnityLightMcpHealthProbeOperation() },
            { "unity.build_target.get", new XUUnityLightMcpBuildTargetGetOperation() },
            { "unity.build_target.switch", new XUUnityLightMcpBuildTargetSwitchOperation() },
            { "unity.editor.quit", new XUUnityLightMcpEditorQuitOperation() },
            { "unity.package.install_test_framework", new XUUnityLightMcpInstallTestFrameworkOperation() },
            { "unity.project.refresh", new XUUnityLightMcpProjectRefreshOperation() },
            { XUUnityLightMcpProjectActionCurrencyOperation.RegisteredOperationName, new XUUnityLightMcpProjectActionCurrencyOperation() },
            { "unity.edm4u.resolve", new XUUnityLightMcpEdm4uResolveOperation() },
            { "unity.sdk.android_resolve", new XUUnityLightMcpSdkAndroidResolveOperation() },
            { "unity.sdk.dependency.verify", new XUUnityLightMcpSdkDependencyVerifyOperation() },
            { "unity.console.tail", new XUUnityLightMcpConsoleTailOperation() },
            { "unity.console.grep", new XUUnityLightMcpConsoleGrepOperation() },
            { "unity.scene.snapshot", new XUUnityLightMcpSceneSnapshotOperation() },
            { "unity.scene.open", new XUUnityLightMcpSceneOpenOperation() },
            { "unity.scene.assert", new XUUnityLightMcpSceneAssertOperation() },
            { "unity.prefab.snapshot", new XUUnityLightMcpPrefabSnapshotOperation() },
            { "unity.asset.snapshot", new XUUnityLightMcpAssetSnapshotOperation() },
            { "unity.prefab.validate", new XUUnityLightMcpPrefabValidateOperation() },
            { "unity.prefab.mutate", new XUUnityLightMcpPrefabMutateOperation() },
            { "unity.ui.tree_snapshot", new XUUnityLightMcpUiTreeSnapshotOperation() },
            { "unity.ui.query", new XUUnityLightMcpUiQueryOperation() },
            { "unity.ui.exists", new XUUnityLightMcpUiExistsOperation() },
            { "unity.ui.get_text", new XUUnityLightMcpUiGetTextOperation() },
            { "unity.ui.get_bounds", new XUUnityLightMcpUiGetBoundsOperation() },
            { "unity.playmode.state", new XUUnityLightMcpPlayModeStateOperation() },
            { "unity.playmode.set", new XUUnityLightMcpPlayModeSetOperation() },
            { "unity.game_view.configure", new XUUnityLightMcpGameViewConfigureOperation() },
            { "unity.game_view.screenshot", new XUUnityLightMcpGameViewScreenshotOperation() },
            { "unity.compile.player_scripts", new XUUnityLightMcpCompilePlayerScriptsOperation() },
            { "unity.compile.matrix", new XUUnityLightMcpCompileMatrixOperation() },
            { "unity.build_player", new XUUnityLightMcpBuildPlayerOperation() },
            { "unity.scenario.validate", new XUUnityLightMcpScenarioValidateOperation() },
            { "unity.scenario.run", new XUUnityLightMcpScenarioRunOperation() },
            { "unity.scenario.result", new XUUnityLightMcpScenarioResultOperation() }
        };

        public static bool TryGet(string operationName, out IXUUnityLightMcpOperation operation)
        {
            return Operations.TryGetValue(operationName, out operation);
        }

        public static void Register(IXUUnityLightMcpOperation operation)
        {
            if (operation == null || string.IsNullOrWhiteSpace(operation.OperationName))
            {
                return;
            }

            Operations[operation.OperationName] = operation;
        }
    }
}
