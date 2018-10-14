import sys as _sys
import google.protobuf.text_format as text_format
from six import text_type as _text_type
import argparse

'''
The definition of pytorch loaded model JUST FOR TEST
'''
import torch
import torch.nn as nn
from torch.autograd import Variable

MAXFEATURES = 30000
EMBEDSIZE = 125
NUMHIDDEN = 100
BATCHSIZE = 64
class SymbolModule(nn.Module):
    def __init__(self, 
                 maxf=MAXFEATURES, edim=EMBEDSIZE, nhid=NUMHIDDEN):
        
        super(SymbolModule, self).__init__()
        self.embedding = nn.Embedding(num_embeddings=maxf,
                                      embedding_dim=edim)
        # If batch-first then input and output 
        # provided as (batch, seq, features)
        # Cudnn used by default if possible
        self.gru = nn.GRU(input_size=edim, 
                          hidden_size=nhid, 
                          num_layers=1,
                          batch_first=True,
                          bidirectional=False)   
        self.l_out = nn.Linear(in_features=nhid*1,
                               out_features=2)

    def forward(self, x, nhid=NUMHIDDEN, batchs=BATCHSIZE):
        x = self.embedding(x)
        h0 = Variable(torch.zeros(1, batchs, nhid))
        x, h = self.gru(x, h0)  # outputs, states
        # just get the last output state
        x = x[:,-1,:].squeeze()
        x = self.l_out(x)
        return x


def _convert(args):
    if args.inputShape != None:
        inputshape = []
        for x in args.inputShape:
            shape = x.split(',')
            inputshape.append([int(x) for x in shape])
    else:
        inputshape = [None]
    if args.srcFramework == 'caffe':
        from mmdnn.conversion.caffe.transformer import CaffeTransformer
        transformer = CaffeTransformer(args.network, args.weights, "tensorflow", inputshape[0], phase = args.caffePhase)
        graph = transformer.transform_graph()
        data = transformer.transform_data()

        from mmdnn.conversion.caffe.writer import JsonFormatter, ModelSaver, PyWriter
        JsonFormatter(graph).dump(args.dstPath + ".json")
        print ("IR network structure is saved as [{}.json].".format(args.dstPath))

        prototxt = graph.as_graph_def().SerializeToString()
        with open(args.dstPath + ".pb", 'wb') as of:
            of.write(prototxt)
        print ("IR network structure is saved as [{}.pb].".format(args.dstPath))

        import numpy as np
        with open(args.dstPath + ".npy", 'wb') as of:
            np.save(of, data)
        print ("IR weights are saved as [{}.npy].".format(args.dstPath))

        return 0

    elif args.srcFramework == 'caffe2':
        raise NotImplementedError("Caffe2 is not supported yet.")

    elif args.srcFramework == 'keras':
        if args.network != None:
            model = (args.network, args.weights)
        else:
            model = args.weights

        from mmdnn.conversion.keras.keras2_parser import Keras2Parser
        parser = Keras2Parser(model)

    elif args.srcFramework == 'tensorflow' or args.srcFramework == 'tf':
        assert args.network or args.weights
        if not args.network:
            if args.dstNodeName is None:
                raise ValueError("Need to provide the output node of Tensorflow model.")
            if args.inNodeName is None:
                raise ValueError("Need to provide the input node of Tensorflow model.")
            if inputshape is None:
                raise ValueError("Need to provide the input node shape of Tensorflow model.")
            assert len(args.inNodeName) == len(inputshape)
            from mmdnn.conversion.tensorflow.tensorflow_frozenparser import TensorflowParser2
            parser = TensorflowParser2(args.weights, inputshape, args.inNodeName, args.dstNodeName)

        else:
            from mmdnn.conversion.tensorflow.tensorflow_parser import TensorflowParser
            if args.inNodeName and inputshape[0]:
                parser = TensorflowParser(args.network, args.weights, args.dstNodeName, inputshape[0], args.inNodeName)
            else:
                parser = TensorflowParser(args.network, args.weights, args.dstNodeName)

    elif args.srcFramework == 'mxnet':
        assert inputshape != None
        if args.weights == None:
            model = (args.network, inputshape[0])
        else:
            import re
            if re.search('.', args.weights):
                args.weights = args.weights[:-7]
            prefix, epoch = args.weights.rsplit('-', 1)
            model = (args.network, prefix, epoch, inputshape[0])

        from mmdnn.conversion.mxnet.mxnet_parser import MXNetParser
        parser = MXNetParser(model)

    elif args.srcFramework == 'cntk':
        from mmdnn.conversion.cntk.cntk_parser import CntkParser
        model = args.network or args.weights
        parser = CntkParser(model)

    elif args.srcFramework == 'pytorch':
        assert inputshape != None
        from mmdnn.conversion.pytorch.pytorch_parser import PytorchParser
        model = args.network or args.weights
        assert model != None
        parser = PytorchParser(model, inputshape[0])

    elif args.srcFramework == 'torch' or args.srcFramework == 'torch7':
        from mmdnn.conversion.torch.torch_parser import TorchParser
        model = args.network or args.weights
        assert model != None
        parser = TorchParser(model, inputshape[0])

    elif args.srcFramework == 'onnx':
        from mmdnn.conversion.onnx.onnx_parser import ONNXParser
        parser = ONNXParser(args.network)

    elif args.srcFramework == 'darknet':
        from mmdnn.conversion.darknet.darknet_parser import DarknetParser
        parser = DarknetParser(args.network, args.weights, args.darknetStart)

    elif args.srcFramework == 'coreml':
        from mmdnn.conversion.coreml.coreml_parser import CoremlParser
        parser = CoremlParser(args.network)

    else:
        raise ValueError("Unknown framework [{}].".format(args.srcFramework))

    parser.run(args.dstPath)

    return 0


def _get_parser():
    import argparse

    parser = argparse.ArgumentParser(description = 'Convert other model file formats to IR format.')

    parser.add_argument(
        '--srcFramework', '-f',
        type=_text_type,
        choices=["caffe", "caffe2", "cntk", "mxnet", "keras", "tensorflow", 'tf', 'torch', 'torch7', 'onnx', 'darknet', 'coreml', 'pytorch'],
        help="Source toolkit name of the model to be converted.")

    parser.add_argument(
        '--weights', '-w', '-iw',
        type=_text_type,
        default=None,
        help='Path to the model weights file of the external tool (e.g caffe weights proto binary, keras h5 binary')

    parser.add_argument(
        '--network', '-n', '-in',
        type=_text_type,
        default=None,
        help='Path to the model network file of the external tool (e.g caffe prototxt, keras json')

    parser.add_argument(
        '--dstPath', '-d', '-o',
        type=_text_type,
        required=True,
        help='Path to save the IR model.')

    parser.add_argument(
        '--inNodeName', '-inode',
        nargs='+',
        type=_text_type,
        default=None,
        help="[Tensorflow] Input nodes' name of the graph.")

    parser.add_argument(
        '--dstNodeName', '-node',
        nargs='+',
        type=_text_type,
        default=None,
        help="[Tensorflow] Output nodes' name of the graph.")

    parser.add_argument(
        '--inputShape',
        nargs='+',
        type=_text_type,
        default=None,
        help='[Tensorflow/MXNet/Caffe2/Torch7] Input shape of model (channel, height, width)')


    # Caffe
    parser.add_argument(
        '--caffePhase',
        type=_text_type,
        default='TRAIN',
        help='[Caffe] Convert the specific phase of caffe model.')


    # Darknet
    parser.add_argument(
        '--darknetStart',
        type=_text_type,
        choices=["0", "1"], 
        help='[Darknet] Parse the darkent model weight file from the start.')

    return parser


def _main():
    # parser = _get_parser()
    # args = parser.parse_args()
    # print(args)
    # args = argparse.Namespace(caffePhase='TRAIN', darknetStart=None, dstNodeName='gru_1', dstPath='keras_TF_RNN', inNodeName='embedding_1_input', inputShape=None, network='C:\\Users\\15501\\Documents\\GitHub\\DeepLearningFrameworks\\notebooks\\keras_TF_RNN_model.json', srcFramework='keras', weights='C:\\Users\\15501\\Documents\\GitHub\\DeepLearningFrameworks\\notebooks\\keras_TF_RNN_weights.h5')
    # args = argparse.Namespace(caffePhase='TRAIN', darknetStart=None, dstNodeName=['transpose'], dstPath='reddit', inNodeName=['Placeholder'], inputShape=['40,40'], network=None, srcFramework='tensorflow', weights='D:\\reddit.pb')
    # args = argparse.Namespace(caffePhase='TRAIN', darknetStart=None, dstNodeName=['rnnlm_1/transpose'], dstPath='reditt', inNodeName='Placeholder:0', inputShape=None, network='C:\\Users\\v-yucli\\Documents\\GitHub\\chatbot-rnn\\models\\new_save\\model.ckpt-5.meta', srcFramework='tensorflow', weights='C:\\Users\\v-yucli\\Documents\\GitHub\\chatbot-rnn\\models\\new_save\\model.ckpt-5')
    #pytorch rnn
    args = argparse.Namespace(caffePhase='TRAIN', darknetStart=None, dstNodeName=None, dstPath='pytorch_RNN', inNodeName=None, inputShape=['64,150'], network='C:\\Users\\v-yucli\\Documents\\pytorch_RNN.pth', srcFramework='pytorch', weights=None)
    ret = _convert(args)
    _sys.exit(int(ret)) # cast to int or else the exit code is always 1


if __name__ == '__main__':
    _main()
