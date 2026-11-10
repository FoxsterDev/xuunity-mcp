using System;
using System.IO;
using NUnit.Framework;
using UnityEngine;
using XUUnity.LightMcp.Editor.Helpers;

namespace XUUnity.LightMcp.Tests.EditMode
{
    [Category("XUUnity.MCP.SelfTest")]
    [Category("XUUnity.MCP.EditMode")]
    [Category("XUUnity.MCP.Fast")]
    public sealed class XUUnityLightMcpCliTestProgressEditModeTests
    {
        string _path;
        string _previousPath;
        Func<int> _previousPid;
        XUUnityLightMcpCliTestProgressState _previousState;

        [SetUp]
        public void SetUp()
        {
            _path = Path.Combine(Path.GetTempPath(), $"xuunity_cli_progress_{Guid.NewGuid():N}.json");
            _previousPath = XUUnityLightMcpCliTestProgress.PathOverride;
            _previousPid = XUUnityLightMcpCliTestProgress.ProcessIdProvider;
            _previousState = XUUnityLightMcpCliTestProgress.ReplaceStateForTests(null);
            XUUnityLightMcpCliTestProgress.PathOverride = _path;
            XUUnityLightMcpCliTestProgress.ProcessIdProvider = () => 4242;
        }

        [TearDown]
        public void TearDown()
        {
            XUUnityLightMcpCliTestProgress.ReplaceStateForTests(_previousState);
            XUUnityLightMcpCliTestProgress.PathOverride = _previousPath;
            XUUnityLightMcpCliTestProgress.ProcessIdProvider = _previousPid;
            if (File.Exists(_path))
            {
                File.Delete(_path);
            }
        }

        static XUUnityLightMcpCliTestProgressState ReadSidecar(string path)
        {
            return JsonUtility.FromJson<XUUnityLightMcpCliTestProgressState>(File.ReadAllText(path));
        }

        [Test]
        public void OnlyBatchRunTestsProcessesAreTracked()
        {
            Assert.That(XUUnityLightMcpCliTestProgress.ShouldTrack(true, new[] { "Unity", "-batchmode", "-runTests" }), Is.True);
            Assert.That(XUUnityLightMcpCliTestProgress.ShouldTrack(false, new[] { "Unity", "-runTests" }), Is.False);
            Assert.That(XUUnityLightMcpCliTestProgress.ShouldTrack(true, new[] { "Unity", "-batchmode", "-executeMethod", "X.Y" }), Is.False);
            Assert.That(
                XUUnityLightMcpCliTestProgress.ShouldTrack(true, new[] { "Unity", "-runTests", "-name", "AssetImportWorker0" }),
                Is.False);
            Assert.That(
                XUUnityLightMcpCliTestProgress.ResolveTestPlatform(new[] { "-runTests", "-testPlatform", "PlayMode" }),
                Is.EqualTo("PlayMode"));
        }

        [Test]
        public void ProgressSurvivesADomainReloadInTheSameProcess()
        {
            XUUnityLightMcpCliTestProgress.RunStarted(3, "PlayMode");
            XUUnityLightMcpCliTestProgress.TestStarted("Suite.First");
            XUUnityLightMcpCliTestProgress.TestFinished("Suite.First", "passed");

            XUUnityLightMcpCliTestProgress.ReplaceStateForTests(null);
            XUUnityLightMcpCliTestProgress.TestStarted("Suite.Second");
            var mid = ReadSidecar(_path);
            Assert.That(mid.run_phase, Is.EqualTo("running"));
            Assert.That(mid.domain_reload_count, Is.EqualTo(1));
            Assert.That(mid.finished, Is.EqualTo(1));
            Assert.That(mid.last_started_test, Is.EqualTo("Suite.Second"));
            Assert.That(mid.test_platform, Is.EqualTo("PlayMode"));

            XUUnityLightMcpCliTestProgress.TestFinished("Suite.Second", "failed");
            XUUnityLightMcpCliTestProgress.RunFinished("failed");
            var done = ReadSidecar(_path);
            Assert.That(done.run_phase, Is.EqualTo("completed"));
            Assert.That(done.total, Is.EqualTo(3));
            Assert.That(done.passed, Is.EqualTo(1));
            Assert.That(done.failed, Is.EqualTo(1));
            Assert.That(done.result_status, Is.EqualTo("failed"));
            Assert.That(done.process_id, Is.EqualTo(4242));
        }

        [Test]
        public void AnotherProcessesSidecarIsNotResumed()
        {
            XUUnityLightMcpCliTestProgress.RunStarted(2, "EditMode");
            XUUnityLightMcpCliTestProgress.ReplaceStateForTests(null);
            XUUnityLightMcpCliTestProgress.ProcessIdProvider = () => 5151;
            XUUnityLightMcpCliTestProgress.TestStarted("Suite.Other");
            var state = ReadSidecar(_path);
            Assert.That(state.process_id, Is.EqualTo(5151));
            Assert.That(state.domain_reload_count, Is.EqualTo(0));
        }
    }
}
