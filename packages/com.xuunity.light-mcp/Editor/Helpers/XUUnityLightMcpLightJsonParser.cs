using System;
using System.Globalization;
using System.Text;

namespace XUUnity.LightMcp.Editor.Helpers
{
    sealed class LightJsonParser
    {
        readonly string _json;
        int _index;

        public LightJsonParser(string json)
        {
            _json = json ?? "";
        }

        public LightJsonNode Parse()
        {
            SkipWhitespace();
            var value = ParseValue();
            SkipWhitespace();
            if (_index != _json.Length)
            {
                throw Error("Unexpected trailing JSON content.");
            }

            return value;
        }

        LightJsonNode ParseValue()
        {
            SkipWhitespace();
            if (_index >= _json.Length)
            {
                throw Error("Unexpected end of JSON.");
            }

            var c = _json[_index];
            return c switch
            {
                '{' => ParseObject(),
                '[' => ParseArray(),
                '"' => LightJsonNode.String(ParseString()),
                't' => ParseLiteral("true", new LightJsonNode { Kind = LightJsonKind.Bool, BoolValue = true }),
                'f' => ParseLiteral("false", new LightJsonNode { Kind = LightJsonKind.Bool, BoolValue = false }),
                'n' => ParseLiteral("null", new LightJsonNode { Kind = LightJsonKind.Null }),
                '-' or >= '0' and <= '9' => ParseNumber(),
                _ => throw Error($"Unexpected JSON character '{c}'."),
            };
        }

        LightJsonNode ParseObject()
        {
            Expect('{');
            var node = LightJsonNode.ObjectNode();
            SkipWhitespace();
            if (TryConsume('}'))
            {
                return node;
            }

            while (true)
            {
                SkipWhitespace();
                var key = ParseString();
                SkipWhitespace();
                Expect(':');
                node.Object[key] = ParseValue();
                SkipWhitespace();
                if (TryConsume('}'))
                {
                    return node;
                }

                Expect(',');
            }
        }

        LightJsonNode ParseArray()
        {
            Expect('[');
            var node = LightJsonNode.ArrayNode();
            SkipWhitespace();
            if (TryConsume(']'))
            {
                return node;
            }

            while (true)
            {
                node.Array.Add(ParseValue());
                SkipWhitespace();
                if (TryConsume(']'))
                {
                    return node;
                }

                Expect(',');
            }
        }

        LightJsonNode ParseNumber()
        {
            var start = _index;
            if (Peek('-'))
            {
                _index++;
            }

            ReadDigits();
            if (Peek('.'))
            {
                _index++;
                ReadDigits();
            }

            if (Peek('e') || Peek('E'))
            {
                _index++;
                if (Peek('+') || Peek('-'))
                {
                    _index++;
                }

                ReadDigits();
            }

            return new LightJsonNode
            {
                Kind = LightJsonKind.Number,
                NumberValue = _json.Substring(start, _index - start),
            };
        }

        LightJsonNode ParseLiteral(string literal, LightJsonNode value)
        {
            if (_index + literal.Length > _json.Length
                || !string.Equals(_json.Substring(_index, literal.Length), literal, StringComparison.Ordinal))
            {
                throw Error($"Expected JSON literal '{literal}'.");
            }

            _index += literal.Length;
            return value;
        }

        string ParseString()
        {
            Expect('"');
            var builder = new StringBuilder();
            while (_index < _json.Length)
            {
                var c = _json[_index++];
                if (c == '"')
                {
                    return builder.ToString();
                }

                if (c != '\\')
                {
                    builder.Append(c);
                    continue;
                }

                if (_index >= _json.Length)
                {
                    throw Error("Unterminated JSON string escape.");
                }

                var escaped = _json[_index++];
                switch (escaped)
                {
                    case '"':
                    case '\\':
                    case '/':
                        builder.Append(escaped);
                        break;
                    case 'b':
                        builder.Append('\b');
                        break;
                    case 'f':
                        builder.Append('\f');
                        break;
                    case 'n':
                        builder.Append('\n');
                        break;
                    case 'r':
                        builder.Append('\r');
                        break;
                    case 't':
                        builder.Append('\t');
                        break;
                    case 'u':
                        builder.Append(ParseUnicodeEscape());
                        break;
                    default:
                        throw Error($"Unsupported JSON string escape '\\{escaped}'.");
                }
            }

            throw Error("Unterminated JSON string.");
        }

        char ParseUnicodeEscape()
        {
            if (_index + 4 > _json.Length)
            {
                throw Error("Incomplete JSON unicode escape.");
            }

            var hex = _json.Substring(_index, 4);
            if (!int.TryParse(hex, NumberStyles.HexNumber, CultureInfo.InvariantCulture, out var codePoint))
            {
                throw Error("Invalid JSON unicode escape.");
            }

            _index += 4;
            return (char)codePoint;
        }

        void ReadDigits()
        {
            var start = _index;
            while (_index < _json.Length && _json[_index] >= '0' && _json[_index] <= '9')
            {
                _index++;
            }

            if (_index == start)
            {
                throw Error("Expected JSON number digit.");
            }
        }

        bool Peek(char c)
        {
            return _index < _json.Length && _json[_index] == c;
        }

        bool TryConsume(char c)
        {
            if (!Peek(c))
            {
                return false;
            }

            _index++;
            return true;
        }

        void Expect(char c)
        {
            if (!TryConsume(c))
            {
                throw Error($"Expected JSON character '{c}'.");
            }
        }

        void SkipWhitespace()
        {
            while (_index < _json.Length && char.IsWhiteSpace(_json[_index]))
            {
                _index++;
            }
        }

        Exception Error(string message)
        {
            return new FormatException($"{message} At offset {_index}.");
        }
    }
}
