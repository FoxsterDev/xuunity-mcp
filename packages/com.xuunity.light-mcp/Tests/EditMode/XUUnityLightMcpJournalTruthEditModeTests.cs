using System;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using UnityEngine;
using XUUnity.LightMcp.Editor.Bridge;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;

namespace XUUnity.LightMcp.Tests.EditMode
{
    [Category("XUUnity.MCP.SelfTest")]
    [Category("XUUnity.MCP.EditMode")]
    [Category("XUUnity.MCP.Fast")]
    public sealed class XUUnityLightMcpJournalTruthEditModeTests
    {
        static XUUnityLightMcpPersistedTestRunState PendingPlayModeRun(string requestId)
        {
            return new XUUnityLightMcpPersistedTestRunState
            {
                request_id = requestId,
                operation = "unity.tests.run_playmode",
                response_handoff_state = "pending",
                completed_at_utc = "",
            };
        }

        [Test]
        public void PendingPlayModeRun_ResumesAfterPlayEntryReload()
        {
            Assert.That(XUUnityLightMcpTestRunState.IsResumablePlayModeRun(PendingPlayModeRun("r1"), "r1"), Is.True);
        }

        [Test]
        public void CompletedOrForeignOrEditModeRun_DoesNotResume()
        {
            var completed = PendingPlayModeRun("r1");
            completed.completed_at_utc = "2026-11-09T10:00:00Z";
            var editMode = PendingPlayModeRun("r1");
            editMode.operation = "unity.tests.run_editmode";

            Assert.That(XUUnityLightMcpTestRunState.IsResumablePlayModeRun(completed, "r1"), Is.False);
            Assert.That(XUUnityLightMcpTestRunState.IsResumablePlayModeRun(PendingPlayModeRun("r1"), "r2"), Is.False);
            Assert.That(XUUnityLightMcpTestRunState.IsResumablePlayModeRun(editMode, "r1"), Is.False);
            Assert.That(XUUnityLightMcpTestRunState.IsResumablePlayModeRun(null, "r1"), Is.False);
        }

        [Test]
        public void BuildPlayerMark_IsBusyUntilCompleted()
        {
            Assume.That(XUUnityLightMcpBuildPlayerRuntime.InProgress, Is.False);
            XUUnityLightMcpBuildPlayerRuntime.MarkStarted("Android");
            try
            {
                Assert.That(XUUnityLightMcpBuildPlayerRuntime.InProgress, Is.True);
                Assert.That(XUUnityLightMcpBuildPlayerRuntime.Target, Is.EqualTo("Android"));
                Assert.That(XUUnityLightMcpBuildPlayerRuntime.BusyReason, Is.EqualTo("build_player"));
            }
            finally
            {
                XUUnityLightMcpBuildPlayerRuntime.MarkCompleted();
            }

            Assert.That(XUUnityLightMcpBuildPlayerRuntime.InProgress, Is.False);
        }

        [Test]
        public void BuildPlayerMark_ClearsOnTheFirstTickAfterAnAbortedBuild()
        {
            Assume.That(XUUnityLightMcpBuildPlayerRuntime.InProgress, Is.False);
            XUUnityLightMcpBuildPlayerRuntime.MarkStarted("iOS");
            XUUnityLightMcpBuildPlayerRuntime.Tick();
            Assert.That(XUUnityLightMcpBuildPlayerRuntime.InProgress, Is.False);
        }

        [Test]
        public void RunPastItsBudget_IsClassifiedAsOverrun()
        {
            Assert.That(
                XUUnityLightMcpTestRunState.ExceededRuntimeBudget("2026-10-05T14:44:00Z", "2026-10-05T15:00:44Z", 900000),
                Is.True);
            Assert.That(
                XUUnityLightMcpTestRunState.ExceededRuntimeBudget("2026-10-05T14:44:00Z", "2026-10-05T14:50:00Z", 900000),
                Is.False);
            Assert.That(XUUnityLightMcpTestRunState.ExceededRuntimeBudget("", "2026-10-05T14:50:00Z", 900000), Is.False);
            Assert.That(
                XUUnityLightMcpTestRunState.CompletedAfterRuntimeBudget,
                Is.EqualTo("completed_after_runtime_budget"));
        }

        [Test]
        public void RecoveredCompletion_IsJournaledOnlyWhenNoCompletionExists()
        {
            var completedId = "selftest-f6-" + Guid.NewGuid().ToString("N");
            var startedOnlyId = "selftest-f6-" + Guid.NewGuid().ToString("N");
            var written = new List<string>();
            try
            {
                written.Add(WriteJournalEventFile(completedId, "request_started"));
                written.Add(WriteJournalEventFile(completedId, "request_completed"));
                written.Add(WriteJournalEventFile(startedOnlyId, "request_started"));

                Assert.That(XUUnityLightMcpTestRunState.ShouldJournalRecoveredCompletion(completedId), Is.False);
                Assert.That(XUUnityLightMcpTestRunState.ShouldJournalRecoveredCompletion(startedOnlyId), Is.True);
                Assert.That(XUUnityLightMcpTestRunState.ShouldJournalRecoveredCompletion(""), Is.False);
            }
            finally
            {
                foreach (var path in written)
                {
                    File.Delete(path);
                }
            }
        }

        static string WriteJournalEventFile(string requestId, string eventType)
        {
            XUUnityLightMcpFileIpcPaths.EnsureDirectories();
            var path = Path.Combine(
                XUUnityLightMcpFileIpcPaths.RequestJournalDirectory,
                "19700101T000000000Z_" + Guid.NewGuid().ToString("N") + "_" + eventType + ".json");
            var payload = new XUUnityLightMcpRequestJournalEvent { event_type = eventType, request_id = requestId };
            File.WriteAllText(path, JsonUtility.ToJson(payload));
            return path;
        }
    }
}
