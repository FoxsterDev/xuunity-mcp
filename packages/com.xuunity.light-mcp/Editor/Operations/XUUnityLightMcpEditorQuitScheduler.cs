using System;
using System.Globalization;
using UnityEditor;
using UnityEngine;
using XUUnity.LightMcp.Editor.Bridge;

namespace XUUnity.LightMcp.Editor.Operations
{
    internal static class XUUnityLightMcpEditorQuitScheduler
    {
        internal const string QuitMechanism = "editor_update_one_shot";
        internal const double IntentLifetimeSeconds = 120d;

        const string RequestIdKey = "XUUnityLightMcp.EditorQuit.RequestId";
        const string ArmedUtcKey = "XUUnityLightMcp.EditorQuit.ArmedUtc";
        const string ExpiresUtcTicksKey = "XUUnityLightMcp.EditorQuit.ExpiresUtcTicks";

        internal static Action<int> ExitAction = EditorApplication.Exit;
        internal static Action<string> JournalExecutingAction = XUUnityLightMcpRequestJournal.WriteEditorQuitExecuting;
        internal static Action<string, string> JournalExpiredAction = XUUnityLightMcpRequestJournal.WriteEditorQuitExpired;
        internal static Action<string> LogAction = message => Debug.Log(message);
        internal static Action<Exception> LogExceptionAction = exception => Debug.LogException(exception);

        static bool _pending;

        internal static bool IsPending => _pending;
        internal static bool HasStoredIntent => !string.IsNullOrEmpty(SessionState.GetString(ExpiresUtcTicksKey, ""));
        internal static string StoredRequestId => SessionState.GetString(RequestIdKey, "");

        internal static DateTime Arm(string requestId)
        {
            return Arm(requestId, DateTime.UtcNow);
        }

        internal static DateTime Arm(string requestId, DateTime armedUtc)
        {
            var expiresUtc = armedUtc.AddSeconds(IntentLifetimeSeconds);
            SessionState.SetString(RequestIdKey, requestId ?? "");
            SessionState.SetString(ArmedUtcKey, FormatUtc(armedUtc));
            SessionState.SetString(ExpiresUtcTicksKey, expiresUtc.Ticks.ToString(CultureInfo.InvariantCulture));
            _pending = true;
            return expiresUtc;
        }

        internal static void RestoreFromSessionState()
        {
            _pending = HasStoredIntent;
        }

        internal static void Disarm()
        {
            SessionState.EraseString(RequestIdKey);
            SessionState.EraseString(ArmedUtcKey);
            SessionState.EraseString(ExpiresUtcTicksKey);
            _pending = false;
        }

        internal static void Tick()
        {
            if (!_pending)
            {
                return;
            }

            var requestId = StoredRequestId;
            var armedUtc = SessionState.GetString(ArmedUtcKey, "");
            var hasExpiry = long.TryParse(
                SessionState.GetString(ExpiresUtcTicksKey, ""),
                NumberStyles.Integer,
                CultureInfo.InvariantCulture,
                out var expiresTicks);
            Disarm();
            if (!hasExpiry)
            {
                return;
            }

            if (DateTime.UtcNow.Ticks >= expiresTicks)
            {
                try
                {
                    JournalExpiredAction(requestId, armedUtc);
                }
                catch
                {
                }
                return;
            }

            try
            {
                JournalExecutingAction(requestId);
            }
            catch
            {
            }

            try
            {
                LogAction($"[XUUnityLightMcp] editor quit executing request_id={requestId}");
            }
            catch
            {
            }

            try
            {
                ExitAction(0);
            }
            catch (Exception ex)
            {
                LogExceptionAction(ex);
            }
        }

        internal static string FormatUtc(DateTime value)
        {
            return value.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture);
        }
    }
}
