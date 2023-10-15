using System;
using System.IO;

namespace VhsDecodeAutoAudioAlign
{
    static class Extensions
    {
        public static FileInfo File(this DirectoryInfo me, string name)
        {
            return new FileInfo(Path.Combine(me.FullName, name));
        }

        public static DirectoryInfo Dir(this DirectoryInfo me, string name)
        {
            return new DirectoryInfo(Path.Combine(me.FullName, name));
        }
    }
}
