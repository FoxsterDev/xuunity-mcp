using System;
using UnityEditor;
using UnityEditor.TestTools.TestRunner.Api;
using UnityEngine;

namespace XUUnity.LightMcp.Editor.Helpers
{
    internal sealed class XUUnityLightMcpCliTestProgressCallbacks : ICallbacks
    {
        readonly string _testPlatform;

        public XUUnityLightMcpCliTestProgressCallbacks(string testPlatform)
        {
            _testPlatform = testPlatform ?? "";
        }

        public void RunStarted(ITestAdaptor testsToRun)
        {
            XUUnityLightMcpCliTestProgress.RunStarted(XUUnityLightMcpPersistedTestCallbacks.CountLeafTests(testsToRun), _testPlatform);
        }

        public void RunFinished(ITestResultAdaptor result)
        {
            XUUnityLightMcpCliTestProgress.RunFinished(result == null ? "" : result.TestStatus.ToString().ToLowerInvariant());
        }

        public void TestStarted(ITestAdaptor test)
        {
            if (test == null || test.IsSuite)
            {
                return;
            }

            XUUnityLightMcpCliTestProgress.TestStarted(test.FullName ?? test.Name ?? "");
        }

        public void TestFinished(ITestResultAdaptor result)
        {
            if (result?.Test == null || result.Test.IsSuite)
            {
                return;
            }

            XUUnityLightMcpCliTestProgress.TestFinished(
                result.Test.FullName ?? result.Test.Name ?? "",
                XUUnityLightMcpPersistedTestCallbacks.NormalizeStatus(result.TestStatus));
        }
    }

    [InitializeOnLoad]
    internal static class XUUnityLightMcpCliTestProgressRegistration
    {
        static XUUnityLightMcpCliTestProgressRegistration()
        {
            var arguments = Environment.GetCommandLineArgs();
            if (!XUUnityLightMcpCliTestProgress.ShouldTrack(Application.isBatchMode, arguments))
            {
                return;
            }

            try
            {
                var api = ScriptableObject.CreateInstance<TestRunnerApi>();
                api.RegisterCallbacks(new XUUnityLightMcpCliTestProgressCallbacks(XUUnityLightMcpCliTestProgress.ResolveTestPlatform(arguments)));
            }
            catch
            {
            }
        }
    }
}
