using System;
using System.IO;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;

namespace VhsDecodeAutoAudioAlign.TbcJson
{
    [DataContract]
    internal class TbcJsonDocument
    {
        [DataContract]
        internal class VideoParameters
        {
            [DataMember]
            public uint numberOfSequentialFields;
            [DataMember]
            public string system;
        }

        [DataContract]
        internal class Field
        {
            [DataMember]
            public bool isFirstField;
            [DataMember]
            public uint seqNo;
            [DataMember]
            public ulong fileLoc;
        }

        [DataMember]
        public VideoParameters videoParameters;

        [DataMember]
        public Field[] fields;
    }

    class TbcJsonReader
    {
        readonly ILog log;

        public TbcJsonReader(ILog log)
        {
            this.log = log ?? throw new ArgumentNullException(nameof(log));
        }

        public TbcJsonDocument ReadTbcJson(FileInfo json)
        {
            if (json == null)
                throw new ArgumentNullException(nameof(json));

            json.Refresh();
            if (json.Exists == false)
                throw new FileNotFoundException(json.FullName);

            var ser = new DataContractJsonSerializer(typeof(TbcJsonDocument));

            using (var strm = json.Open(FileMode.Open, FileAccess.Read, FileShare.Read))
                return (TbcJsonDocument)ser.ReadObject(strm);
        }
    }
}
