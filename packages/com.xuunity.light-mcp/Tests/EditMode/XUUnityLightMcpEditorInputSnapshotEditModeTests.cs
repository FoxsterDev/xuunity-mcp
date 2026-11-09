using System;
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
    public sealed class XUUnityLightMcpEditorInputSnapshotEditModeTests
    {
        static readonly DateTime CompiledUtc = new(2026, 11, 5, 16, 45, 0, DateTimeKind.Utc);
        static readonly DateTime EditedUtc = new(2026, 11, 5, 16, 59, 0, DateTimeKind.Utc);
        string _root;
        string _outsidePackage;

        [SetUp]
        public void SetUp()
        {
            _root = Path.Combine(Path.GetTempPath(), "XUUnityMcpInputSnapshot" + Guid.NewGuid().ToString("N"));
            _outsidePackage = Path.Combine(Path.GetTempPath(), "XUUnityMcpLocalPackage" + Guid.NewGuid().ToString("N"));
            Write("Assets/Scripts/Board.cs", "class Board {}");
            Write("Packages/com.example.core/package.json", "{}");
            Write("Packages/com.example.core/Runtime/JsonUtils.cs", "class JsonUtils {}");
            Write("Packages/com.example.core/Samples~/Ignored.cs", "class Ignored {}");
            Directory.CreateDirectory(_outsidePackage);
            File.WriteAllText(Path.Combine(_outsidePackage, "package.json"), "{}");
            File.WriteAllText(Path.Combine(_outsidePackage, "Shared.cs"), "class Shared {}");
            File.SetLastWriteTimeUtc(Path.Combine(_outsidePackage, "Shared.cs"), CompiledUtc.AddMinutes(-5));
            Write(
                "Packages/manifest.json",
                "{\"dependencies\":{\"com.example.shared\":\"file:" + _outsidePackage.Replace("\\", "\\\\")
                + "\",\"com.example.tarball\":\"file:Tarballs/x-1.0.0.tgz\"}}");
        }

        [TearDown]
        public void TearDown()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, true);
            }

            if (Directory.Exists(_outsidePackage))
            {
                Directory.Delete(_outsidePackage, true);
            }
        }

        [Test]
        public void ScanCoversAssetsEmbeddedAndLocalPackagesButNotIgnoredOrTarballEntries()
        {
            var snapshot = XUUnityLightMcpEditorInputSnapshot.CaptureSnapshot(_root, CompiledUtc);

            Assert.That(snapshot.Hashes.Keys, Does.Contain("Assets/Scripts/Board.cs"));
            Assert.That(snapshot.Hashes.Keys, Does.Contain("Packages/com.example.core/Runtime/JsonUtils.cs"));
            Assert.That(snapshot.Hashes.Keys, Has.Some.EndsWith("Shared.cs"));
            Assert.That(snapshot.Hashes.Keys, Has.None.Contains("Samples~"));
            Assert.That(snapshot.Hashes.Count, Is.EqualTo(3));
            Assert.That(snapshot.DirtyAtCapture, Is.Empty);
        }

        [Test]
        public void TouchWithoutContentChangeStaysCurrentWithoutAnyRefresh()
        {
            var snapshot = XUUnityLightMcpEditorInputSnapshot.CaptureSnapshot(_root, CompiledUtc);
            File.SetLastWriteTimeUtc(Path.Combine(_root, "Packages/com.example.core/Runtime/JsonUtils.cs"), EditedUtc);

            var comparison = Compare(snapshot);
            var currency = Classify(comparison);

            Assert.That(comparison.changed_count, Is.Zero);
            Assert.That(currency, Is.EqualTo("current"));
            Assert.That(_reason, Is.EqualTo("editor_inputs_touched_without_content_change"));
            Assert.That(_basis, Is.EqualTo("compiled_editor_input_content_snapshot"));
        }

        [Test]
        public void ContentEditInAnEmbeddedPackageReadsStaleEvenAfterASettledForcedRefresh()
        {
            var snapshot = XUUnityLightMcpEditorInputSnapshot.CaptureSnapshot(_root, CompiledUtc);
            Write("Packages/com.example.core/Runtime/JsonUtils.cs", "class JsonUtils { int warm; }");
            File.SetLastWriteTimeUtc(Path.Combine(_root, "Packages/com.example.core/Runtime/JsonUtils.cs"), EditedUtc);

            var comparison = Compare(snapshot);
            var currency = XUUnityLightMcpProjectActionCurrency.ClassifyEditorDomainCurrency(
                "2026-11-05T16:46:00.0000000Z",
                comparison.newest_write_utc,
                true,
                "2026-11-05T17:09:00.0000000Z",
                false,
                comparison.state,
                comparison.changed_count,
                out var current,
                out var known,
                out var reason,
                out var basis);

            Assert.That(currency, Is.EqualTo("stale"));
            Assert.That(current, Is.False);
            Assert.That(known, Is.True);
            Assert.That(reason, Is.EqualTo("editor_input_content_changed_since_compile"));
            Assert.That(basis, Is.EqualTo("compiled_editor_input_content_snapshot"));
            CollectionAssert.AreEqual(new[] { "Packages/com.example.core/Runtime/JsonUtils.cs" }, comparison.changed_paths);
        }

        [Test]
        public void AddedDeletedAndDirtyAtCaptureInputsAllCountAsChanged()
        {
            File.SetLastWriteTimeUtc(Path.Combine(_root, "Assets/Scripts/Board.cs"), EditedUtc);
            var snapshot = XUUnityLightMcpEditorInputSnapshot.CaptureSnapshot(_root, CompiledUtc);
            File.Delete(Path.Combine(_root, "Packages/com.example.core/Runtime/JsonUtils.cs"));
            Write("Assets/Tests/NewTests.cs", "class NewTests {}");

            var comparison = Compare(snapshot);

            Assert.That(comparison.Ready, Is.True);
            Assert.That(comparison.changed_count, Is.EqualTo(3));
            Assert.That(comparison.changed_paths, Does.Contain("Assets/Scripts/Board.cs"));
            Assert.That(comparison.changed_paths, Does.Contain("Assets/Tests/NewTests.cs"));
            Assert.That(comparison.changed_paths, Does.Contain("Packages/com.example.core/Runtime/JsonUtils.cs"));
        }

        [Test]
        public void FailedCompilationWithUnchangedContentFallsBackToTheLegacyRule()
        {
            var currency = XUUnityLightMcpProjectActionCurrency.ClassifyEditorDomainCurrency(
                "2026-11-05T16:46:00.0000000Z",
                "2026-11-05T16:59:00.0000000Z",
                true,
                "",
                true,
                XUUnityLightMcpEditorInputSnapshot.StateReady,
                0,
                out _,
                out _,
                out var reason,
                out var basis);

            Assert.That(currency, Is.EqualTo("stale"));
            Assert.That(reason, Is.EqualTo("assets_editor_input_newer_than_loaded_editor_domain_with_failed_script_compilation"));
            Assert.That(basis, Is.EqualTo("editor_domain_load_vs_newest_assets_editor_input"));
        }

        [Test]
        public void DomainBasisUsesTheCompileStartWhenItPrecedesTheDomainLoad()
        {
            var loaded = new DateTime(2026, 11, 5, 17, 22, 5, DateTimeKind.Utc);

            Assert.That(
                XUUnityLightMcpEditorInputSnapshot.ResolveDomainBasisUtc("2026-11-05T17:21:40.0000000Z", loaded),
                Is.EqualTo(new DateTime(2026, 11, 5, 17, 21, 40, DateTimeKind.Utc)));
            Assert.That(XUUnityLightMcpEditorInputSnapshot.ResolveDomainBasisUtc("", loaded), Is.EqualTo(loaded));
            Assert.That(
                XUUnityLightMcpEditorInputSnapshot.ResolveDomainBasisUtc("2026-11-05T18:00:00.0000000Z", loaded),
                Is.EqualTo(loaded));
        }

        [Test]
        public void PersistedSnapshotRoundTripsPathsHashesAndCompileOutcome()
        {
            Write("Assets/Scripts/Dirty.cs", "class Dirty {}");
            File.SetLastWriteTimeUtc(Path.Combine(_root, "Assets/Scripts/Dirty.cs"), EditedUtc);
            var snapshot = XUUnityLightMcpEditorInputSnapshot.CaptureSnapshot(_root, CompiledUtc);
            var path = XUUnityLightMcpEditorInputSnapshot.PersistedSnapshotPath(_root);

            var persisted = XUUnityLightMcpEditorInputSnapshot.ToPersisted(
                snapshot,
                XUUnityLightMcpEditorInputSnapshot.TriggerCompilationFinished,
                XUUnityLightMcpEditorInputSnapshot.CompileOutcomeFailed,
                2,
                4242);
            Assert.That(XUUnityLightMcpEditorInputSnapshot.TryPersist(path, persisted), Is.True);

            var read = JsonUtility.FromJson<XUUnityLightMcpPersistedEditorInputSnapshot>(File.ReadAllText(path));
            Assert.That(read.trigger, Is.EqualTo("compilation_finished"));
            Assert.That(read.compile_outcome, Is.EqualTo("failed"));
            Assert.That(read.compile_error_count, Is.EqualTo(2));
            Assert.That(read.editor_pid, Is.EqualTo(4242));
            Assert.That(read.basis_utc, Is.EqualTo("2026-11-05T16:45:00.0000000Z"));
            Assert.That(read.paths.Count, Is.EqualTo(4));
            Assert.That(read.hashes.Count, Is.EqualTo(4));
            var boardIndex = read.paths.IndexOf("Assets/Scripts/Board.cs");
            Assert.That(read.hashes[boardIndex], Is.EqualTo(snapshot.Hashes["Assets/Scripts/Board.cs"]));
            Assert.That(read.dirty_at_capture, Is.EqualTo(new[] { "Assets/Scripts/Dirty.cs" }));
        }

        [Test]
        public void HashMatchesTheHostFnvVectors()
        {
            Write("Assets/a.bin", "a");
            Write("Assets/foobar.bin", "foobar");

            Assert.That(XUUnityLightMcpEditorInputSnapshot.HashFile(Path.Combine(_root, "Assets/a.bin")), Is.EqualTo("1:af63dc4c8601ec8c"));
            Assert.That(XUUnityLightMcpEditorInputSnapshot.HashFile(Path.Combine(_root, "Assets/foobar.bin")), Is.EqualTo("6:85944171f73967e8"));
        }

        [Test]
        public void ImportWorkerProcessesAreNotCaptured()
        {
            Assert.That(XUUnityLightMcpEditorInputSnapshot.ShouldCapture(XUUnityLightMcpBridgeProcessIdentity.ImportWorkerProcessClass), Is.False);
            Assert.That(XUUnityLightMcpEditorInputSnapshot.ShouldCapture(XUUnityLightMcpBridgeProcessIdentity.MainEditorProcessClass), Is.True);
            Assert.That(XUUnityLightMcpEditorInputSnapshot.ShouldCapture(XUUnityLightMcpBridgeProcessIdentity.BatchProcessClass), Is.True);
        }

        [Test]
        public void TheLiveProjectSnapshotIsPersistedForThisEditor()
        {
            var projectRoot = XUUnityLightMcpFileIpcPaths.ProjectRootPath;
            XUUnityLightMcpEditorInputSnapshot.Compare(projectRoot);
            var path = XUUnityLightMcpEditorInputSnapshot.PersistedSnapshotPath(projectRoot);

            Assert.That(File.Exists(path), Is.True, path);
            var read = JsonUtility.FromJson<XUUnityLightMcpPersistedEditorInputSnapshot>(File.ReadAllText(path));
            Assert.That(read.trigger, Is.AnyOf("domain_load", "compilation_finished"));
            Assert.That(read.editor_pid, Is.EqualTo(System.Diagnostics.Process.GetCurrentProcess().Id));
            Assert.That(read.paths.Count, Is.EqualTo(read.hashes.Count));
            Assert.That(read.paths.Count, Is.EqualTo(read.input_count));
        }

        string _reason;
        string _basis;

        string Classify(XUUnityLightMcpEditorInputComparison comparison)
        {
            return XUUnityLightMcpProjectActionCurrency.ClassifyEditorDomainCurrency(
                "2026-11-05T16:46:00.0000000Z",
                comparison.newest_write_utc,
                true,
                "",
                false,
                comparison.state,
                comparison.changed_count,
                out _,
                out _,
                out _reason,
                out _basis);
        }

        XUUnityLightMcpEditorInputComparison Compare(XUUnityLightMcpEditorInputSnapshot.Snapshot snapshot)
        {
            var comparison = new XUUnityLightMcpEditorInputComparison();
            XUUnityLightMcpEditorInputSnapshot.CompareWith(snapshot, _root, comparison);
            return comparison;
        }

        void Write(string relative, string content)
        {
            var path = Path.Combine(_root, relative);
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            File.WriteAllText(path, content);
            File.SetLastWriteTimeUtc(path, CompiledUtc.AddMinutes(-10));
        }
    }
}
