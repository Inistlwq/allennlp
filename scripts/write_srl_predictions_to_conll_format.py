import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(os.path.join(__file__, os.pardir))))
import argparse

from allennlp.common.tqdm import Tqdm
from allennlp.common import Params
from allennlp.data.iterators import BasicIterator
from allennlp.data import DatasetReader
from allennlp.models import Model
from allennlp.models.semantic_role_labeler import write_to_conll_eval_file
from allennlp.modules.elmo import Elmo

# We need to inport these here so they get Registered.
from calypso.token_embedders import GatedCNNTokenEmbedder, TransformerTokenEmbedder

def main(serialization_directory: int,
         device: int,
         data: str,
         prefix: str,
         domain: str = None):
    """
    serialization_directory : str, required.
        the directory containing the serialized weights.
    device: int, default = -1
        the device to run the evaluation on.
    data: str, default = None
        The data to evaluate on. By default, we use the validation data from
        the original experiment.
    prefix: str, default=""
        The prefix to prepend to the generated gold and prediction files, to distinguish
        different models/data.
    domain: str, optional (default = None)
        If passed, filters the ontonotes evaluation/test dataset to only contain the
        specified domain.
    """
    config = Params.from_file(os.path.join(serialization_directory, "config.json"))

    if domain is not None:
       config["dataset_reader"]["domain_identifier"] = domain
       prefix = f"{domain}_{prefix}"

    else:
       config["dataset_reader"].pop("domain_identifier", None)

    dataset_reader = DatasetReader.from_params(config['dataset_reader'])

    evaluation_data_path = data if data else config['validation_data_path']

    model = Model.load(config, serialization_dir=serialization_directory, cuda_device=device)
    model.eval()

    prediction_file_path = os.path.join(serialization_directory, prefix + "_predictions.txt")
    gold_file_path = os.path.join(serialization_directory, prefix + "_gold.txt")
    prediction_file = open(prediction_file_path, "w+")
    gold_file = open(gold_file_path, "w+")

    # load the evaluation data and index it.
    print("reading evaluation data from {}".format(evaluation_data_path))
    instances = dataset_reader.read(evaluation_data_path)
    iterator = BasicIterator(batch_size=32)
    iterator.index_with(model.vocab)

    model_predictions = []
    batches = iterator(instances, num_epochs=1, shuffle=False, cuda_device=device, for_training=False)
    for batch in Tqdm.tqdm(batches):
        result = model(**batch)
        predictions = model.decode(result)
        model_predictions.extend(predictions["tags"])

    for instance, prediction in zip(instances, model_predictions):
        fields = instance.fields
        try:
            # most sentences have a verbal predicate, but not all.
            verb_index = fields["verb_indicator"].labels.index(1)
        except ValueError:
            verb_index = None

        gold_tags = fields["tags"].labels
        sentence = [x.text for x in fields["tokens"].tokens]

        write_to_conll_eval_file(prediction_file, gold_file,
                                 verb_index, sentence, prediction, gold_tags)
    prediction_file.close()
    gold_file.close()

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="write conll format srl predictions"
                                                 " to file from a pretrained model.")
    parser.add_argument('--path', type=str, help='the serialization directory.')
    parser.add_argument('--device', type=int, default=-1, help='the device to load the model onto.')
    parser.add_argument('--data', type=str, default=None, help='A directory containing a dataset to evaluate on.')
    parser.add_argument('--prefix', type=str, default="", help='A prefix to distinguish model outputs.')
    parser.add_argument('--domain', type=str, default=None, help='An optional domain to filter by for producing results.')
    args = parser.parse_args()
    main(args.path, args.device, args.data, args.prefix, args.domain)
