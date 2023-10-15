using System;
using System.IO;
using System.Linq;
using NUnit.Framework;
using VhsDecodeAutoAudioAlign.Io;

namespace VhsDecodeAutoAudioAlign.Test.UnitTest.io
{
    [TestFixture]
    class InputStreamCacheTest
    {
        ConsoleLog log;

        [SetUp]
        public void Init()
        {
            log = new ConsoleLog();
        }

        [TearDown]
        public void Cleanup()
        {
        }

        static InputStreamCacheConfig DefaultCfg => new InputStreamCacheConfig()
        {
            sampleSizeInBytes = 2,
            blockSizeInSamples = 2,
            blocksToCache = 2,
        };

        static byte[] GetFakeSample(int n)
        {
            var v = (byte)(n & 0xff);
            var s = new byte[DefaultCfg.sampleSizeInBytes];
            for (int i = 0; i < s.Length; ++i)
                s[i] = v;
            return s;
        }

        static MemoryStream GetFakeDataStream(int samples)
        {
            var data = Enumerable
                .Range(0, samples)
                .SelectMany(i => GetFakeSample(i))
                .ToArray();

            Console.WriteLine("fake sample data " + data.Length);
            var stream = new MemoryStream(data);
            return stream;
        }

        [Test]
        public void GetSampleStreamedRead([Values(1, 100, 1000)] int samples, [Values(1, 2)] int jitter)
        {
            var stream = GetFakeDataStream(samples);
            var cut = new InputStreamCache(log, stream, DefaultCfg);

            for (int i = 0; i < samples; ++i)
            {
                for (int j = (-1 * jitter); j < jitter; ++j)
                {
                    var sampleLocation = i + j;
                    if (sampleLocation < 0)
                        sampleLocation = 0;
                    else if (sampleLocation >= samples)
                        sampleLocation = (samples - 1);

                    var next = cut.GetSample((ulong)sampleLocation);

                    Assert.That(next.Length, Is.EqualTo(DefaultCfg.sampleSizeInBytes));
                    for (int n = 0; n < DefaultCfg.sampleSizeInBytes; ++n)
                        Assert.That(next[n], Is.EqualTo(sampleLocation & 0xff), "Sample [" + sampleLocation + "] Byte [" + n + "]");
                }
            }
        }


        [Test]
        public void GetSampleOutOfCache()
        {
            var stream = GetFakeDataStream(1000);
            var cut = new InputStreamCache(log, stream, DefaultCfg);

            var next = cut.GetSample(900);
            Assert.NotNull(next);

            Assert.Throws<IOException>(() => cut.GetSample(0));
        }
    }
}
