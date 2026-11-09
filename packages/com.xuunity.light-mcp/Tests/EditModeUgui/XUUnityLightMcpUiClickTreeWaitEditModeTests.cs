using System;
using System.Collections;
using System.IO;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UI;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;
using XUUnity.LightMcp.Editor.Ugui;
using Object = UnityEngine.Object;

namespace XUUnity.LightMcp.Tests.EditModeUgui
{
    [Category("XUUnity.MCP.SelfTest")]
    [Category("XUUnity.MCP.EditMode")]
    [Category("XUUnity.MCP.UiInteraction")]
    public sealed class XUUnityLightMcpUiClickTreeWaitEditModeTests
    {
        const int MaxTestFrames = 400;

        GameObject _canvasRoot;
        GameObject _popup;
        bool _clicked;
        string _requestId = "";

        [SetUp]
        public void SetUp()
        {
            XUUnityLightMcpUiClickTreeWatch.Clear();
            _clicked = false;
            _requestId = "ui-click-wait-selftest-" + Guid.NewGuid().ToString("N");
            _canvasRoot = new GameObject(
                "XUUnityMcp_TreeWaitEditCanvas",
                typeof(RectTransform),
                typeof(Canvas),
                typeof(GraphicRaycaster));
            _canvasRoot.GetComponent<Canvas>().renderMode = RenderMode.ScreenSpaceOverlay;
            _canvasRoot.GetComponent<RectTransform>().sizeDelta = new Vector2(1080f, 1920f);

            var opener = new GameObject("OpenButton", typeof(RectTransform), typeof(Image));
            opener.transform.SetParent(_canvasRoot.transform, false);
            opener.GetComponent<RectTransform>().sizeDelta = new Vector2(300f, 120f);
            opener.AddComponent<Button>().onClick.AddListener(() => _clicked = true);

            _popup = new GameObject("LatePopup", typeof(RectTransform), typeof(Image));
            _popup.transform.SetParent(_canvasRoot.transform, false);
            _popup.GetComponent<RectTransform>().anchoredPosition = new Vector2(0f, 600f);
            _popup.SetActive(false);
        }

        [TearDown]
        public void TearDown()
        {
            XUUnityLightMcpUiClickTreeWatch.Clear();
            var outbox = OutboxPath(_requestId);
            if (File.Exists(outbox))
            {
                File.Delete(outbox);
            }

            if (_canvasRoot != null)
            {
                Object.DestroyImmediate(_canvasRoot);
            }
        }

        [UnityTest]
        public IEnumerator DirectClick_WithWindow_AnswersAsynchronouslyOnceTheTreeChanges()
        {
            var response = Execute(_requestId, 3000);
            Assert.That(response, Is.Null, "an unchanged tree with a window defers the answer");
            Assert.That(_clicked, Is.True);
            Assert.That(XUUnityLightMcpUiClickTreeWatch.IsPending, Is.True);

            var frames = 0;
            while (!File.Exists(OutboxPath(_requestId)))
            {
                Assert.That(++frames, Is.LessThan(MaxTestFrames), "the deferred click never answered");
                if (frames == 3)
                {
                    _popup.SetActive(true);
                }

                yield return null;
                XUUnityLightMcpUiClickTreeWatch.Tick();
            }

            var written = JsonUtility.FromJson<XUUnityLightMcpResponse>(File.ReadAllText(OutboxPath(_requestId)));
            Assert.That(written.status, Is.EqualTo("ok"));
            var payload = JsonUtility.FromJson<XUUnityLightMcpUiClickPayload>(written.payload_json);
            Assert.That(payload.status, Is.EqualTo("effective"));
            Assert.That(payload.state_changed, Is.True);
            Assert.That(payload.tree_change_wait_status, Is.EqualTo(XUUnityLightMcpUiClickTreeWatch.ChangedAfterWait));
            Assert.That(payload.tree_change_sample_count, Is.GreaterThan(0));
            Assert.That(XUUnityLightMcpUiClickTreeWatch.IsPending, Is.False);
        }

        [Test]
        public void DirectClick_WhileAnotherWaits_IsRefusedBeforeDelivery()
        {
            Assert.That(Execute(_requestId, 3000), Is.Null);
            _clicked = false;

            var second = Execute(_requestId + "-second", 3000);

            Assert.That(second, Is.Not.Null);
            var payload = JsonUtility.FromJson<XUUnityLightMcpUiClickPayload>(second.payload_json);
            Assert.That(payload.refusal_code, Is.EqualTo("ui_click_wait_in_progress"));
            Assert.That(_clicked, Is.False);
        }

        [Test]
        public void DirectClick_WithoutWindow_AnswersInTheDeliveryFrame()
        {
            var response = Execute(_requestId, 0);

            Assert.That(response, Is.Not.Null);
            var payload = JsonUtility.FromJson<XUUnityLightMcpUiClickPayload>(response.payload_json);
            Assert.That(payload.status, Is.EqualTo("delivered_no_observable_effect"));
            Assert.That(payload.tree_change_wait_status, Is.EqualTo(XUUnityLightMcpUiClickTreeWatch.WaitNotRequested));
            Assert.That(XUUnityLightMcpUiClickTreeWatch.IsPending, Is.False);
        }

        static XUUnityLightMcpResponse Execute(string requestId, int waitForTreeChangeMs)
        {
            return new XUUnityLightMcpUiClickOperation().Execute(new XUUnityLightMcpRequest
            {
                request_id = requestId,
                operation = "unity.ui.click",
                args_json = JsonUtility.ToJson(new XUUnityLightMcpUiClickArgs
                {
                    action = "click",
                    approve = true,
                    targetKind = XUUnityLightMcpUiRead.TargetGameObjectName,
                    targetValue = "XUUnityMcp_TreeWaitEditCanvas",
                    waitForTreeChangeMs = waitForTreeChangeMs,
                    selector = new XUUnityLightMcpUiSelectorArgs { name = "OpenButton" }
                })
            });
        }

        static string OutboxPath(string requestId)
        {
            return Path.Combine(XUUnityLightMcpFileIpcPaths.OutboxDirectory, $"{requestId}.json");
        }
    }
}
