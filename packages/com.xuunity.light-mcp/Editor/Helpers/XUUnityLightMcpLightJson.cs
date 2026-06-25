using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace XUUnity.LightMcp.Editor.Helpers
{
    enum LightJsonKind
    {
        Null,
        Object,
        Array,
        String,
        Number,
        Bool,
    }

    sealed class LightJsonNode
    {
        public LightJsonKind Kind;
        public Dictionary<string, LightJsonNode> Object;
        public List<LightJsonNode> Array;
        public string StringValue;
        public string NumberValue;
        public bool BoolValue;

        public static LightJsonNode ObjectNode() => new() { Kind = LightJsonKind.Object, Object = new Dictionary<string, LightJsonNode>(StringComparer.Ordinal) };
        public static LightJsonNode ArrayNode() => new() { Kind = LightJsonKind.Array, Array = new List<LightJsonNode>() };
        public static LightJsonNode String(string value) => new() { Kind = LightJsonKind.String, StringValue = value ?? "" };

        public static bool TryParse(string json, out LightJsonNode node, out string errorMessage)
        {
            node = null;
            errorMessage = "";

            try
            {
                var parser = new LightJsonParser(json ?? "");
                node = parser.Parse();
                return true;
            }
            catch (Exception ex)
            {
                errorMessage = ex.Message;
                return false;
            }
        }

        public bool TryGetObject(string key, out LightJsonNode value)
        {
            return TryGet(key, LightJsonKind.Object, out value);
        }

        public bool TryGetArray(string key, out LightJsonNode value)
        {
            return TryGet(key, LightJsonKind.Array, out value);
        }

        public bool TryGetString(string key, out string value)
        {
            value = "";
            if (Kind != LightJsonKind.Object
                || Object == null
                || !Object.TryGetValue(key, out var node)
                || node.Kind != LightJsonKind.String)
            {
                return false;
            }

            value = node.StringValue ?? "";
            return true;
        }

        public string GetString(string key)
        {
            return TryGetString(key, out var value) ? value : "";
        }

        public bool GetBool(string key)
        {
            return Kind == LightJsonKind.Object
                && Object != null
                && Object.TryGetValue(key, out var node)
                && node.Kind == LightJsonKind.Bool
                && node.BoolValue;
        }

        public LightJsonNode Clone()
        {
            switch (Kind)
            {
                case LightJsonKind.Object:
                {
                    var clone = ObjectNode();
                    foreach (var pair in Object)
                    {
                        clone.Object[pair.Key] = pair.Value.Clone();
                    }

                    return clone;
                }
                case LightJsonKind.Array:
                {
                    var clone = ArrayNode();
                    foreach (var item in Array)
                    {
                        clone.Array.Add(item.Clone());
                    }

                    return clone;
                }
                case LightJsonKind.String:
                    return String(StringValue);
                case LightJsonKind.Number:
                    return new LightJsonNode { Kind = LightJsonKind.Number, NumberValue = NumberValue };
                case LightJsonKind.Bool:
                    return new LightJsonNode { Kind = LightJsonKind.Bool, BoolValue = BoolValue };
                default:
                    return new LightJsonNode { Kind = LightJsonKind.Null };
            }
        }

        public void ReplaceWith(LightJsonNode replacement)
        {
            Kind = replacement.Kind;
            Object = replacement.Object;
            Array = replacement.Array;
            StringValue = replacement.StringValue;
            NumberValue = replacement.NumberValue;
            BoolValue = replacement.BoolValue;
        }

        public string ToJson()
        {
            var builder = new StringBuilder();
            WriteJson(builder);
            return builder.ToString();
        }

        bool TryGet(string key, LightJsonKind expectedKind, out LightJsonNode value)
        {
            value = null;
            return Kind == LightJsonKind.Object
                && Object != null
                && Object.TryGetValue(key, out value)
                && value.Kind == expectedKind;
        }

        void WriteJson(StringBuilder builder)
        {
            switch (Kind)
            {
                case LightJsonKind.Object:
                    builder.Append('{');
                    var firstProperty = true;
                    foreach (var pair in Object)
                    {
                        if (!firstProperty)
                        {
                            builder.Append(',');
                        }

                        WriteEscapedString(builder, pair.Key);
                        builder.Append(':');
                        pair.Value.WriteJson(builder);
                        firstProperty = false;
                    }

                    builder.Append('}');
                    break;
                case LightJsonKind.Array:
                    builder.Append('[');
                    for (var i = 0; i < Array.Count; i++)
                    {
                        if (i > 0)
                        {
                            builder.Append(',');
                        }

                        Array[i].WriteJson(builder);
                    }

                    builder.Append(']');
                    break;
                case LightJsonKind.String:
                    WriteEscapedString(builder, StringValue ?? "");
                    break;
                case LightJsonKind.Number:
                    builder.Append(NumberValue);
                    break;
                case LightJsonKind.Bool:
                    builder.Append(BoolValue ? "true" : "false");
                    break;
                default:
                    builder.Append("null");
                    break;
            }
        }

        static void WriteEscapedString(StringBuilder builder, string value)
        {
            builder.Append('"');
            foreach (var c in value ?? "")
            {
                switch (c)
                {
                    case '"':
                        builder.Append("\\\"");
                        break;
                    case '\\':
                        builder.Append("\\\\");
                        break;
                    case '\b':
                        builder.Append("\\b");
                        break;
                    case '\f':
                        builder.Append("\\f");
                        break;
                    case '\n':
                        builder.Append("\\n");
                        break;
                    case '\r':
                        builder.Append("\\r");
                        break;
                    case '\t':
                        builder.Append("\\t");
                        break;
                    default:
                        if (c < 32 || c > 126)
                        {
                            builder.Append("\\u");
                            builder.Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                        }
                        else
                        {
                            builder.Append(c);
                        }
                        break;
                }
            }

            builder.Append('"');
        }
    }

}
