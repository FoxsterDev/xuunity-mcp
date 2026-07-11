using System;
using System.IO;

namespace XUUnity.LightMcp.Editor.Core
{
    /// <summary>
    /// Publishes IPC files atomically. The Python host polls bridge_state.json,
    /// outbox responses, journal events and batch/scenario results while the
    /// editor writes them; a plain File.WriteAllText lets the poller observe a
    /// half-written file (truncated JSON) or hit a sharing violation mid-write.
    /// Runs on the editor main thread (heartbeat/pump), so it must never sleep
    /// or block: on contention it falls back to the legacy in-place write,
    /// whose torn reads the host's retry-until-deadline reader tolerates.
    /// </summary>
    internal static class XUUnityLightMcpAtomicFileWriter
    {
        const int PublishAttempts = 3;

        public static void WriteAllText(string path, string contents)
        {
            var directory = Path.GetDirectoryName(path);
            if (!string.IsNullOrEmpty(directory))
            {
                Directory.CreateDirectory(directory);
            }

            var tempPath = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
            try
            {
                File.WriteAllText(tempPath, contents);

                for (var attempt = 0; attempt < PublishAttempts; attempt++)
                {
                    try
                    {
                        if (File.Exists(path))
                        {
                            File.Replace(tempPath, path, null);
                        }
                        else
                        {
                            File.Move(tempPath, path);
                        }

                        return;
                    }
                    catch (IOException)
                    {
                        // A poller briefly holds the destination; retry immediately.
                    }
                    catch (UnauthorizedAccessException)
                    {
                    }
                }

                File.WriteAllText(path, contents);
            }
            finally
            {
                TryDelete(tempPath);
            }
        }

        static void TryDelete(string path)
        {
            try
            {
                if (File.Exists(path))
                {
                    File.Delete(path);
                }
            }
            catch (IOException)
            {
            }
            catch (UnauthorizedAccessException)
            {
            }
        }
    }
}
