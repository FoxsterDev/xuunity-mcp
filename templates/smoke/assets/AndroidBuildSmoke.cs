using System;
using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;

public static class AndroidBuildSmoke
{
    private const string SceneDirectory = "Assets/Scenes";
    private const string ScenePath = SceneDirectory + "/Main.unity";
    private const string AndroidApplicationId = "com.xuunity.lightmcp.androidsmoke";

    public static void BuildAndroidApk()
    {
        EnsureSceneExists();

        PlayerSettings.productName = "XUUnityLightMcpAndroidSmoke";
        PlayerSettings.companyName = "XUUnity";
        PlayerSettings.SetApplicationIdentifier(BuildTargetGroup.Android, AndroidApplicationId);

        var outputPath = GetOutputPath();
        var outputDirectory = Path.GetDirectoryName(outputPath);
        if (string.IsNullOrWhiteSpace(outputDirectory))
        {
            throw new Exception($"Could not derive output directory from '{outputPath}'.");
        }

        Directory.CreateDirectory(outputDirectory);

        var buildPlayerOptions = new BuildPlayerOptions
        {
            scenes = new[] { ScenePath },
            locationPathName = outputPath,
            target = BuildTarget.Android,
            options = BuildOptions.None
        };

        var report = BuildPipeline.BuildPlayer(buildPlayerOptions);
        Debug.Log($"Android smoke build result: {report.summary.result}; output: {outputPath}");

        if (report.summary.result != BuildResult.Succeeded)
        {
            throw new Exception(
                $"Android smoke build failed: {report.summary.result}; errors: {report.summary.totalErrors}; output: {outputPath}");
        }
    }

    private static void EnsureSceneExists()
    {
        if (File.Exists(ScenePath))
        {
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };
            return;
        }

        Directory.CreateDirectory(SceneDirectory);
        var scene = EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);

        var camera = GameObject.Find("Main Camera");
        if (camera != null)
        {
            camera.transform.position = new Vector3(0f, 1f, -10f);
        }

        var cube = GameObject.CreatePrimitive(PrimitiveType.Cube);
        cube.name = "SmokeCube";
        cube.transform.position = Vector3.zero;

        EditorSceneManager.SaveScene(scene, ScenePath);
        EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };
        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();
    }

    private static string GetOutputPath()
    {
        var explicitOutputPath = Environment.GetEnvironmentVariable("XUUNITY_SMOKE_APK_PATH");
        if (!string.IsNullOrWhiteSpace(explicitOutputPath))
        {
            return Path.GetFullPath(explicitOutputPath);
        }

        return Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "Build", "android-smoke.apk"));
    }
}
