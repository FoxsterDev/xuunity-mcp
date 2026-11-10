using NUnit.Framework;
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
    }
}
