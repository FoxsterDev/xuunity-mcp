using System;
using System.Diagnostics;
using UnityEngine;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Operations;
using static XUUnity.LightMcp.Editor.Helpers.XUUnityLightMcpNestedOperationClient;

namespace XUUnity.LightMcp.Editor.Helpers
{
    static class XUUnityLightMcpScenarioUiInteractionStepHandler
    {
        const string ClickOperation = "unity.ui.click";

        public static bool ProcessUiReadStep(
            XUUnityLightMcpScenarioStepDefinition step,
            XUUnityLightMcpScenarioStepResult stepResult,
            string operation)
        {
            XUUnityLightMcpPlayModeStateOperation.PopulateLivenessEvidence(stepResult);
            if (XUUnityLightMcpUiSelectorMatcher.IsEmpty(step.selector))
            {
                return Fail(stepResult, "ui_selector_invalid",
                    $"{step.kind} requires a selector with at least one constraint.");
            }

            var args = new XUUnityLightMcpUiQueryArgs
            {
                targetKind = string.IsNullOrWhiteSpace(step.targetKind) ? XUUnityLightMcpUiRead.TargetActiveScene : step.targetKind,
                targetValue = step.targetValue ?? "",
                sceneName = step.sceneName ?? "",
                includeDontDestroyOnLoad = step.includeDontDestroyOnLoad,
                maxDepth = step.maxDepth > 0 ? step.maxDepth : XUUnityLightMcpUiRead.DefaultMaxDepth,
                maxNodes = step.maxNodes > 0 ? step.maxNodes : XUUnityLightMcpUiRead.DefaultMaxNodes,
                maxMatches = XUUnityLightMcpUiRead.DefaultMaxMatches,
                includeInactive = false,
                allowMany = false,
                selector = step.selector
            };

            var stopwatch = Stopwatch.StartNew();
            var response = ExecuteNestedOperation(operation, JsonUtility.ToJson(args));
            stopwatch.Stop();
            stepResult.duration_seconds = Math.Round(stopwatch.Elapsed.TotalSeconds, 6);

            if (response == null)
            {
                return Fail(stepResult, "null_nested_response", $"Nested operation '{operation}' returned no response.");
            }

            if (response.status != "ok")
            {
                return Fail(
                    stepResult,
                    response.error?.code ?? "ui_read_unavailable",
                    response.error?.message ?? $"Nested operation '{operation}' failed.");
            }

            var query = string.IsNullOrWhiteSpace(response.payload_json)
                ? new XUUnityLightMcpUiQueryPayload()
                : JsonUtility.FromJson<XUUnityLightMcpUiQueryPayload>(response.payload_json) ?? new XUUnityLightMcpUiQueryPayload();
            var isExists = string.Equals(operation, "unity.ui.exists", StringComparison.Ordinal);
            var expectedText = step.expectedText ?? "";
            var payload = new XUUnityLightMcpUiReadStepPayload
            {
                operation = operation,
                expected_exists = step.expectedExists,
                expected_text = expectedText,
                query = query
            };

            payload.met_expectations = query.success;
            if (isExists)
            {
                payload.met_expectations = payload.met_expectations
                    && query.exists == step.expectedExists
                    && (!query.truncated || step.expectedExists)
                    && (!query.out_of_scope || step.expectedExists);
            }
            else if (!string.IsNullOrEmpty(expectedText))
            {
                payload.met_expectations = payload.met_expectations
                    && string.Equals(query.text, expectedText, StringComparison.Ordinal);
            }

            stepResult.payload_json = JsonUtility.ToJson(payload);
            if (!payload.met_expectations)
            {
                var diagnostic = query.errors != null && query.errors.Count > 0 ? query.errors[0] : null;
                stepResult.status = "failed";
                stepResult.error_code = diagnostic?.code
                    ?? (isExists ? "ui_exists_expectation_failed" : "ui_text_expectation_failed");
                stepResult.error_message = diagnostic?.message
                    ?? (isExists
                        ? $"Expected selector exists={step.expectedExists}, observed exists={query.exists}."
                        : $"Expected text '{expectedText}', observed '{query.text ?? ""}'.");
                return true;
            }

            stepResult.status = "passed";
            stepResult.outcome = isExists
                ? (query.exists ? "ui_exists_matched" : "ui_absence_confirmed")
                : "ui_text_captured";
            return true;
        }

        public static bool ProcessUiClickStep(
            XUUnityLightMcpScenarioStepDefinition step,
            XUUnityLightMcpScenarioStepResult stepResult)
        {
            XUUnityLightMcpPlayModeStateOperation.PopulateLivenessEvidence(stepResult);
            var interactionId = (step.interactionId ?? "").Trim();
            if (string.IsNullOrEmpty(interactionId))
            {
                return Fail(stepResult, "missing_interaction_id",
                    $"{XUUnityLightMcpUiRead.InteractionStepKind} requires interactionId so a reference can require it by name.");
            }

            if (!step.approve)
            {
                return Fail(stepResult, "ui_click_approval_required",
                    $"{XUUnityLightMcpUiRead.InteractionStepKind} requires approve=true; delivering a click mutates runtime UI state.");
            }

            var args = new XUUnityLightMcpUiClickArgs
            {
                action = "click",
                approve = true,
                targetKind = string.IsNullOrWhiteSpace(step.targetKind) ? XUUnityLightMcpUiRead.TargetActiveScene : step.targetKind,
                targetValue = step.targetValue ?? "",
                sceneName = step.sceneName ?? "",
                includeDontDestroyOnLoad = step.includeDontDestroyOnLoad,
                maxDepth = step.maxDepth > 0 ? step.maxDepth : XUUnityLightMcpUiRead.DefaultMaxDepth,
                maxNodes = step.maxNodes > 0 ? step.maxNodes : XUUnityLightMcpUiRead.DefaultMaxNodes,
                selector = step.selector ?? new XUUnityLightMcpUiSelectorArgs()
            };

            var stopwatch = Stopwatch.StartNew();
            var response = ExecuteNestedOperation(ClickOperation, JsonUtility.ToJson(args));
            stopwatch.Stop();
            stepResult.duration_seconds = Math.Round(stopwatch.Elapsed.TotalSeconds, 6);

            if (response == null)
            {
                return Fail(stepResult, "null_nested_response", $"Nested operation '{ClickOperation}' returned no response.");
            }

            if (response.status != "ok")
            {
                return Fail(
                    stepResult,
                    response.error?.code ?? "ui_click_unavailable",
                    response.error?.message
                        ?? $"'{ClickOperation}' is unavailable; it ships in the uGUI satellite assembly and needs com.unity.ugui.");
            }

            var click = string.IsNullOrWhiteSpace(response.payload_json)
                ? new XUUnityLightMcpUiClickPayload()
                : JsonUtility.FromJson<XUUnityLightMcpUiClickPayload>(response.payload_json) ?? new XUUnityLightMcpUiClickPayload();

            var expectStateChange = step.expectStateChange;
            var payload = new XUUnityLightMcpUiInteractionStepPayload
            {
                expect_state_change = expectStateChange,
                click_status = click.status ?? "",
                click_error = click.refusal_code ?? "",
                ui_interaction = new XUUnityLightMcpUiInteractionBlock
                {
                    interaction_id = interactionId,
                    action = "click",
                    selector = args.selector,
                    delivered = click.delivered,
                    delivery_mechanism = click.delivery_mechanism ?? "",
                    target_path = click.target_node != null ? click.target_node.path : "",
                    target_component = click.target_component ?? "",
                    handler_path = click.delivered_to_path ?? "",
                    pointer_target_status = click.pointer_target_status ?? "",
                    pointer_target_blocked_by = click.pointer_target_blocked_by ?? "",
                    transparent_hit_area = click.transparent_hit_area,
                    transparent_hit_area_evidence = click.transparent_hit_area_evidence ?? "",
                    effective = click.effective,
                    no_observable_effect = click.no_observable_effect,
                    state_changed = click.state_changed,
                    before_signature = click.before_snapshot != null ? click.before_snapshot.signature : "",
                    after_signature = click.after_snapshot != null ? click.after_snapshot.signature : "",
                    search_target = click.search_target ?? new XUUnityLightMcpUiTargetInfo(),
                    search_node_count = click.search_node_count,
                    search_max_depth = click.search_max_depth,
                    search_max_nodes = click.search_max_nodes,
                    search_truncated = click.search_truncated,
                    search_truncation_reason = click.search_truncation_reason ?? "",
                    playmode_state = click.playmode_state ?? "",
                    playmode_loop_liveness = click.playmode_loop_liveness ?? "",
                    playmode_liveness_warning = click.playmode_liveness_warning ?? "",
                    playmode_liveness_remediation = click.playmode_liveness_remediation ?? "",
                    editor_application_focused = click.editor_application_focused,
                    result_trust_class = click.result_trust_class ?? "",
                    refusal_code = click.refusal_code ?? ""
                }
            };

            payload.met_expectations = click.delivered
                && string.IsNullOrEmpty(click.refusal_code)
                && (!expectStateChange || click.state_changed);

            stepResult.payload_json = JsonUtility.ToJson(payload);

            if (!payload.met_expectations)
            {
                stepResult.status = "failed";
                stepResult.error_code = string.IsNullOrEmpty(click.refusal_code)
                    ? (click.delivered ? "ui_interaction_no_state_change" : "ui_interaction_not_delivered")
                    : click.refusal_code;
                stepResult.error_message = DescribeFailure(interactionId, click, expectStateChange);
                return true;
            }

            stepResult.status = "passed";
            stepResult.outcome = click.no_observable_effect ? "delivered_no_observable_effect" : "interaction_delivered";
            return true;
        }

        static string DescribeFailure(string interactionId, XUUnityLightMcpUiClickPayload click, bool expectStateChange)
        {
            if (!string.IsNullOrEmpty(click.refusal_code))
            {
                return $"Interaction '{interactionId}' was refused as {click.refusal_code} before delivery.";
            }

            if (!click.delivered)
            {
                return $"Interaction '{interactionId}' reached a handler but no handler consumed the click.";
            }

            return expectStateChange
                ? $"Interaction '{interactionId}' was delivered but the UI tree did not change; set expectStateChange=false if that is intended."
                : $"Interaction '{interactionId}' did not meet its expectations.";
        }

        static bool Fail(XUUnityLightMcpScenarioStepResult stepResult, string code, string message)
        {
            stepResult.status = "failed";
            stepResult.error_code = code;
            stepResult.error_message = message;
            return true;
        }
    }
}
