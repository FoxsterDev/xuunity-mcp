using System;
using System.Collections.Generic;
using System.Reflection;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;
using UnityEngine.SceneManagement;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Operations;

namespace XUUnity.LightMcp.Tests.EditMode
{
    [Category("XUUnity.MCP.SelfTest")]
    [Category("XUUnity.MCP.EditMode")]
    [Category("XUUnity.MCP.Fast")]
    public sealed class XUUnityLightMcpEditorQuitSchedulerEditModeTests
    {
        const string RequestId = "xuunity-quit-scheduler-selftest";

        Action<int> _originalExitAction;
        Action<string> _originalJournalExecutingAction;
        Action<string, string> _originalJournalExpiredAction;
        Action<string> _originalLogAction;
        Action<Exception> _originalLogExceptionAction;
        Func<bool> _originalPrefabStageDirty;
        List<int> _exitCodes;
        List<bool> _intentStoredAtExit;
        List<string> _events;
        List<Exception> _loggedExceptions;

        [SetUp]
        public void SetUp()
        {
            _originalExitAction = XUUnityLightMcpEditorQuitScheduler.ExitAction;
            _originalJournalExecutingAction = XUUnityLightMcpEditorQuitScheduler.JournalExecutingAction;
            _originalJournalExpiredAction = XUUnityLightMcpEditorQuitScheduler.JournalExpiredAction;
            _originalLogAction = XUUnityLightMcpEditorQuitScheduler.LogAction;
            _originalLogExceptionAction = XUUnityLightMcpEditorQuitScheduler.LogExceptionAction;
            _originalPrefabStageDirty = XUUnityLightMcpEditorQuitOperation.PrefabStageDirty;
            _exitCodes = new List<int>();
            _intentStoredAtExit = new List<bool>();
            _events = new List<string>();
            _loggedExceptions = new List<Exception>();
            XUUnityLightMcpEditorQuitScheduler.Disarm();
            XUUnityLightMcpEditorQuitScheduler.ExitAction = code =>
            {
                _events.Add("exit");
                _exitCodes.Add(code);
                _intentStoredAtExit.Add(
                    XUUnityLightMcpEditorQuitScheduler.IsPending || XUUnityLightMcpEditorQuitScheduler.HasStoredIntent);
            };
            XUUnityLightMcpEditorQuitScheduler.JournalExecutingAction = requestId => _events.Add($"executing:{requestId}");
            XUUnityLightMcpEditorQuitScheduler.JournalExpiredAction =
                (requestId, armedUtc) => _events.Add($"expired:{requestId}:{armedUtc}");
            XUUnityLightMcpEditorQuitScheduler.LogAction = message => _events.Add($"log:{message}");
            XUUnityLightMcpEditorQuitScheduler.LogExceptionAction = exception => _loggedExceptions.Add(exception);
        }

        [TearDown]
        public void TearDown()
        {
            XUUnityLightMcpEditorQuitScheduler.Disarm();
            XUUnityLightMcpEditorQuitScheduler.ExitAction = _originalExitAction;
            XUUnityLightMcpEditorQuitScheduler.JournalExecutingAction = _originalJournalExecutingAction;
            XUUnityLightMcpEditorQuitScheduler.JournalExpiredAction = _originalJournalExpiredAction;
            XUUnityLightMcpEditorQuitScheduler.LogAction = _originalLogAction;
            XUUnityLightMcpEditorQuitScheduler.LogExceptionAction = _originalLogExceptionAction;
            XUUnityLightMcpEditorQuitOperation.PrefabStageDirty = _originalPrefabStageDirty;
        }

        [Test]
        public void ArmThenTick_ExitsOnceAfterClearingIntent()
        {
            XUUnityLightMcpEditorQuitScheduler.Arm(RequestId);

            XUUnityLightMcpEditorQuitScheduler.Tick();

            Assert.That(_exitCodes, Is.EqualTo(new[] { 0 }));
            Assert.That(_intentStoredAtExit, Is.EqualTo(new[] { false }));
            Assert.That(XUUnityLightMcpEditorQuitScheduler.HasStoredIntent, Is.False);
        }

        [Test]
        public void Tick_WritesExecutingWithRequestIdBeforeExit()
        {
            XUUnityLightMcpEditorQuitScheduler.Arm(RequestId);

            XUUnityLightMcpEditorQuitScheduler.Tick();

            Assert.That(_events, Is.EqualTo(new[]
            {
                $"executing:{RequestId}",
                $"log:[XUUnityLightMcp] editor quit executing request_id={RequestId}",
                "exit",
            }));
        }

        [Test]
        public void Tick_SurvivesThrowingJournalAndLogAndStillExits()
        {
            XUUnityLightMcpEditorQuitScheduler.JournalExecutingAction = _ => throw new InvalidOperationException("journal");
            XUUnityLightMcpEditorQuitScheduler.LogAction = _ => throw new InvalidOperationException("log");
            XUUnityLightMcpEditorQuitScheduler.Arm(RequestId);

            Assert.DoesNotThrow(XUUnityLightMcpEditorQuitScheduler.Tick);

            Assert.That(_exitCodes, Is.EqualTo(new[] { 0 }));
            Assert.That(XUUnityLightMcpEditorQuitScheduler.IsPending, Is.False);
            Assert.That(XUUnityLightMcpEditorQuitScheduler.HasStoredIntent, Is.False);
        }

        [Test]
        public void Tick_SurvivesThrowingExitActionAndClearsIntent()
        {
            var failure = new InvalidOperationException("exit");
            XUUnityLightMcpEditorQuitScheduler.ExitAction = _ => throw failure;
            XUUnityLightMcpEditorQuitScheduler.Arm(RequestId);

            Assert.DoesNotThrow(XUUnityLightMcpEditorQuitScheduler.Tick);

            Assert.That(_loggedExceptions, Is.EqualTo(new[] { failure }));
            Assert.That(XUUnityLightMcpEditorQuitScheduler.IsPending, Is.False);
            Assert.That(XUUnityLightMcpEditorQuitScheduler.HasStoredIntent, Is.False);
        }

        [Test]
        public void ExpiredIntent_SurvivesThrowingJournalAndClearsIntent()
        {
            XUUnityLightMcpEditorQuitScheduler.JournalExpiredAction = (_, _) => throw new InvalidOperationException("journal");
            XUUnityLightMcpEditorQuitScheduler.Arm(
                RequestId,
                DateTime.UtcNow.AddSeconds(-(XUUnityLightMcpEditorQuitScheduler.IntentLifetimeSeconds + 80d)));

            Assert.DoesNotThrow(XUUnityLightMcpEditorQuitScheduler.Tick);

            Assert.That(_exitCodes, Is.Empty);
            Assert.That(XUUnityLightMcpEditorQuitScheduler.HasStoredIntent, Is.False);
        }

        [Test]
        public void SecondTick_IsNoOp()
        {
            XUUnityLightMcpEditorQuitScheduler.Arm(RequestId);
            XUUnityLightMcpEditorQuitScheduler.Tick();

            XUUnityLightMcpEditorQuitScheduler.Tick();

            Assert.That(_exitCodes.Count, Is.EqualTo(1));
        }

        [Test]
        public void TickWithoutIntent_IsNoOp()
        {
            XUUnityLightMcpEditorQuitScheduler.Tick();

            Assert.That(_exitCodes, Is.Empty);
        }

        [Test]
        public void ExpiredIntent_IsDroppedWithoutExit()
        {
            var armedUtc = DateTime.UtcNow.AddSeconds(-(XUUnityLightMcpEditorQuitScheduler.IntentLifetimeSeconds + 80d));
            XUUnityLightMcpEditorQuitScheduler.Arm(RequestId, armedUtc);

            XUUnityLightMcpEditorQuitScheduler.Tick();

            Assert.That(_exitCodes, Is.Empty);
            Assert.That(_events, Is.EqualTo(new[]
            {
                $"expired:{RequestId}:{XUUnityLightMcpEditorQuitScheduler.FormatUtc(armedUtc)}",
            }));
            Assert.That(XUUnityLightMcpEditorQuitScheduler.IsPending, Is.False);
            Assert.That(XUUnityLightMcpEditorQuitScheduler.HasStoredIntent, Is.False);
        }

        [Test]
        public void SimulatedDomainReload_RestoresIntentAndExits()
        {
            XUUnityLightMcpEditorQuitScheduler.Arm(RequestId);
            SetPendingFlag(false);

            XUUnityLightMcpEditorQuitScheduler.Tick();
            Assert.That(_exitCodes, Is.Empty);

            XUUnityLightMcpEditorQuitScheduler.RestoreFromSessionState();
            XUUnityLightMcpEditorQuitScheduler.Tick();

            Assert.That(_exitCodes, Is.EqualTo(new[] { 0 }));
        }

        [Test]
        public void QuitOperation_ArmsUpdateOneShotWithoutDelayCall()
        {
            var delayCallsBefore = DelayCallCount();

            var response = new XUUnityLightMcpEditorQuitOperation().Execute(
                new XUUnityLightMcpRequest { request_id = RequestId, operation = "unity.editor.quit" });

            Assert.That(DelayCallCount(), Is.EqualTo(delayCallsBefore));
            Assert.That(response.status, Is.EqualTo("ok"));
            Assert.That(_exitCodes, Is.Empty);
            Assert.That(XUUnityLightMcpEditorQuitScheduler.IsPending, Is.True);
            Assert.That(XUUnityLightMcpEditorQuitScheduler.StoredRequestId, Is.EqualTo(RequestId));
            var payload = JsonUtility.FromJson<XUUnityLightMcpEditorQuitPayload>(response.payload_json);
            Assert.That(payload.quit_mechanism, Is.EqualTo("editor_update_one_shot"));
            Assert.That(payload.quit_expires_at_utc, Is.Not.Empty);
            Assert.That(payload.editor_pid, Is.GreaterThan(0));
        }

        [Test]
        public void QuitOperation_SceneDirtyIncludesPrefabStage()
        {
            XUUnityLightMcpEditorQuitOperation.PrefabStageDirty = () => true;
            Assert.That(ExecuteQuit().scene_dirty, Is.True);

            XUUnityLightMcpEditorQuitOperation.PrefabStageDirty = () => false;
            Assert.That(ExecuteQuit().scene_dirty, Is.EqualTo(AnyLoadedSceneDirty()));
            Assert.That(_exitCodes, Is.Empty);
        }

        static XUUnityLightMcpEditorQuitPayload ExecuteQuit()
        {
            var response = new XUUnityLightMcpEditorQuitOperation().Execute(
                new XUUnityLightMcpRequest { request_id = RequestId, operation = "unity.editor.quit" });
            return JsonUtility.FromJson<XUUnityLightMcpEditorQuitPayload>(response.payload_json);
        }

        static bool AnyLoadedSceneDirty()
        {
            for (var index = 0; index < SceneManager.sceneCount; index++)
            {
                if (SceneManager.GetSceneAt(index).isDirty)
                {
                    return true;
                }
            }

            return false;
        }

        static void SetPendingFlag(bool value)
        {
            typeof(XUUnityLightMcpEditorQuitScheduler)
                .GetField("_pending", BindingFlags.NonPublic | BindingFlags.Static)
                .SetValue(null, value);
        }

        static int DelayCallCount()
        {
            return EditorApplication.delayCall?.GetInvocationList().Length ?? 0;
        }
    }
}
