using System;
using System.IO;
using System.Threading;

namespace XUUnity.LightMcp.Editor.Core
{
    /// <summary>
    /// Publishes IPC files atomically. The Python host polls bridge_state.json,
    /// outbox responses, journal events and batch/scenario results while the
    /// editor writes them; a plain File.WriteAllText lets the poller observe a
    /// half-written file (truncated JSON) or hit a sharing violation mid-write.
    /// </summary>
    internal static class XUUnityLightMcpAtomicFileWriter
    {
        const int PublishAttempts = 5;
        const int PublishRetryDelayMilliseconds = 20;

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
                        // A reader may briefly hold the destination open.
                    }
                    catch (UnauthorizedAccessException)
                    {
                    }

                    Thread.Sleep(PublishRetryDelayMilliseconds);
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
