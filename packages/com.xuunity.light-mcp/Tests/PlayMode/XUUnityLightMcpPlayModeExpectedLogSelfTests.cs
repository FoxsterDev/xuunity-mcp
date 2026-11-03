using System;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

namespace XUUnity.LightMcp.Tests.PlayMode
{
    [Category("XUUnity.MCP.SelfTest")]
    [Category("XUUnity.MCP.PlayMode")]
    [Category("XUUnity.MCP.Fast")]
    [Category("XUUnity.MCP.ExpectedLog")]
    public sealed class XUUnityLightMcpPlayModeExpectedLogSelfTests
    {
        const string ProbeMessage = "xuunity expected-log probe";

        [Test]
        public void ExpectedException_IsConsumedByLogAssert()
        {
            LogAssert.Expect(LogType.Exception, "InvalidOperationException: " + ProbeMessage);
            Debug.LogException(new InvalidOperationException(ProbeMessage));
        }
    }
}
