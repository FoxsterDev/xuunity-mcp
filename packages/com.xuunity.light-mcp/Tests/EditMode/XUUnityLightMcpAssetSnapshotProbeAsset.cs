using System;
using UnityEngine;

namespace XUUnity.LightMcp.Tests.EditMode
{
    public sealed class XUUnityLightMcpAssetSnapshotProbeAsset : ScriptableObject
    {
        public enum ProbeMode
        {
            Off,
            Scout,
            Pivot,
        }

        [Serializable]
        public struct ProbeNested
        {
            public int weight;
            public string label;
        }

        public int intValue = 7;
        public string label = "probe";
        public bool flag = true;
        public float ratio = 0.5f;
        public ProbeMode mode = ProbeMode.Pivot;
        public ProbeNested nested = new ProbeNested { weight = 3, label = "inner" };
        public int[] numbers = { 1, 2, 3 };
    }
}
