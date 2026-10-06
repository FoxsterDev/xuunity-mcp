using System.IO;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;
using UnityEngine.UI;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Operations;

namespace XUUnity.LightMcp.Tests.EditModeUgui
{
    [Category("XUUnity.MCP.SelfTest")]
    [Category("XUUnity.MCP.EditMode")]
    [Category("XUUnity.MCP.Fast")]
    [Category("XUUnity.MCP.PrefabMutation")]
    public sealed class XUUnityLightMcpPrefabMutationSpriteReferenceTests
    {
        const string FIXTURE_DIR = "Assets/XUUnityLightMcpGenerated/MutationSpriteSelfTest";
        const string ROOT_NAME = "XUUnityMcp_SpriteRoot";
        const string SPRITE_NAME = "XUUnityMcp_SingleSprite";
        const string TEXTURE_PATH = FIXTURE_DIR + "/" + SPRITE_NAME + ".png";
        const string PREFAB_PATH = FIXTURE_DIR + "/" + ROOT_NAME + ".prefab";

        [SetUp]
        public void SetUp()
        {
            Directory.CreateDirectory(FIXTURE_DIR);
            var texture = new Texture2D(4, 4);
            File.WriteAllBytes(TEXTURE_PATH, texture.EncodeToPNG());
            Object.DestroyImmediate(texture);
            AssetDatabase.Refresh();

            var importer = (TextureImporter)AssetImporter.GetAtPath(TEXTURE_PATH);
            importer.textureType = TextureImporterType.Sprite;
            importer.spriteImportMode = SpriteImportMode.Single;
            importer.SaveAndReimport();

            var root = new GameObject(ROOT_NAME, typeof(RectTransform), typeof(Image));
            PrefabUtility.SaveAsPrefabAsset(root, PREFAB_PATH);
            Object.DestroyImmediate(root);
            AssetDatabase.Refresh();
        }

        [TearDown]
        public void TearDown()
        {
            AssetDatabase.DeleteAsset(FIXTURE_DIR);
            AssetDatabase.Refresh();
        }

        [Test]
        public void ASingleModeSpriteIsResolvedByNameEvenThoughItsTextureSharesThatName()
        {
            Assert.That(AssetDatabase.LoadMainAssetAtPath(TEXTURE_PATH).name, Is.EqualTo(SPRITE_NAME));
            Assert.That(AssetDatabase.LoadAssetAtPath<Sprite>(TEXTURE_PATH).name, Is.EqualTo(SPRITE_NAME));

            var payload = Mutate("m_Sprite", TEXTURE_PATH + "#" + SPRITE_NAME);

            Assert.That(payload.status, Is.EqualTo("applied"), payload.changes[0].error_message);
            Assert.That(payload.changes[0].after, Is.EqualTo(TEXTURE_PATH + "#" + SPRITE_NAME));
            Assert.That(SavedSprite(), Is.EqualTo(AssetDatabase.LoadAssetAtPath<Sprite>(TEXTURE_PATH)));
        }

        [Test]
        public void APlainTexturePathResolvesToItsOnlySpriteForASpriteField()
        {
            var payload = Mutate("m_Sprite", TEXTURE_PATH);

            Assert.That(payload.status, Is.EqualTo("applied"), payload.changes[0].error_message);
            Assert.That(SavedSprite(), Is.EqualTo(AssetDatabase.LoadAssetAtPath<Sprite>(TEXTURE_PATH)));
        }

        [Test]
        public void ANameMatchOfTheWrongTypeIsStillATypeMismatch()
        {
            var payload = Mutate("m_Material", TEXTURE_PATH + "#" + SPRITE_NAME);

            Assert.That(payload.status, Is.EqualTo("rolled_back"));
            Assert.That(payload.changes[0].error_code, Is.EqualTo("prefab_mutation_asset_type_mismatch"));
        }

        static Sprite SavedSprite()
        {
            return AssetDatabase.LoadAssetAtPath<GameObject>(PREFAB_PATH).GetComponent<Image>().sprite;
        }

        static XUUnityLightMcpPrefabMutationPayload Mutate(string propertyPath, string reference)
        {
            var args = "{\"prefabPath\":\"" + PREFAB_PATH + "\",\"approve\":true,\"previewOnly\":false,\"operations\":["
                       + "{\"op\":\"set_serialized_field\",\"path\":\"" + ROOT_NAME + "\",\"componentType\":\"Image\","
                       + "\"propertyPath\":\"" + propertyPath + "\",\"stringValue\":\"" + reference + "\"}]}";
            var response = new XUUnityLightMcpPrefabMutateOperation().Execute(new XUUnityLightMcpRequest
            {
                request_id = "prefab-mutate-sprite-selftest",
                operation = "unity.prefab.mutate",
                args_json = args
            });
            Assert.That(response.status, Is.EqualTo("ok"));
            return JsonUtility.FromJson<XUUnityLightMcpPrefabMutationPayload>(response.payload_json);
        }
    }
}
