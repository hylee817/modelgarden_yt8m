"""Video classification configuration definition."""
from typing import Optional, Tuple
import dataclasses
from official.core import config_definitions as cfg
from official.core import exp_factory
from official.modeling import hyperparams
from official.modeling import optimization
from official.vision.beta.configs import common
from absl import flags
FLAGS = flags.FLAGS

# Default values
YT8M_TRAIN_EXAMPLES = 4000
YT8M_VAL_EXAMPLES = 1000
# 2/frame -> frame level
# 3/frame -> segment level #todo: if segment_labels = True -> check if using 3/frame dataset
YT8M_TRAIN_PATH = 'gs://youtube8m-ml/2/frame/train/train*.tfrecord'
YT8M_VAL_PATH = 'gs://youtube8m-ml/3/frame/validate/validate*.tfrecord'
YT8M_TEST_PATH = 'gs://youtube8m-ml/3/frame/test/test*.tfrecord'

@dataclasses.dataclass
class DataConfig(cfg.DataConfig):
  """The base configuration for building datasets."""
  name: Optional[str] = 'yt8m'
  split: str = None
  feature_sizes: Tuple[int, ...] = (1024, 128)
  feature_names: Tuple[str, ...] = ("rgb", "audio")
  segment_size: int = 1
  segment_labels: bool = False
  temporal_stride: int = 1
  max_frames: int = 300
  num_frames: int = 300 # set smaller to allow random sample (Parser)
  num_classes: int = 3862
  num_devices: int = 1    #todo: remove
  input_path: str = ''
  is_training: bool = True
  random_seed: int = 123
  num_examples: int = -1


def yt8m(is_training):
  """ YT8M dataset configs. """
  return DataConfig(
    num_frames=30,
    temporal_stride=1,
    segment_labels=False,
    segment_size=5,
    is_training=is_training,
    split='train' if is_training else 'valid',
    num_examples=YT8M_TRAIN_EXAMPLES if is_training
    else YT8M_VAL_EXAMPLES,
    input_path=YT8M_TRAIN_PATH if is_training
    else YT8M_VAL_PATH
  )


@dataclasses.dataclass
class YT8MModel(hyperparams.Config):
  """The model config."""
  # iterations : int = 30     # Number of frames per batch
  cluster_size : int = 8192
  hidden_size : int = 1024
  add_batch_norm : bool = True
  sample_random_frames : bool = True
  is_training : bool = True
  activation : str = "sigmoid"
  pooling_method : str = "max"
  yt8m_agg_classifier_model : str = "MoeModel"

@dataclasses.dataclass
class Losses(hyperparams.Config):
  name: str = 'binary_crossentropy'
  from_logits: bool = False
  label_smoothing: float = 0.0

@dataclasses.dataclass
class YT8MTask(cfg.TaskConfig):
  """The task config."""
  model: YT8MModel = YT8MModel()
  train_data: DataConfig = yt8m(is_training=True)
  validation_data: DataConfig = yt8m(is_training=False)
  losses: Losses = Losses()
  gradient_clip_norm: float = 1.0
  num_readers: int = 8
  top_k: int = 20
  top_n: int = None

def add_trainer(experiment: cfg.ExperimentConfig,
                train_batch_size: int,
                eval_batch_size: int,
                learning_rate: float = 0.01,
                train_epochs: int = 44,
                ):
  """Add and config a trainer to the experiment config."""
  if YT8M_TRAIN_EXAMPLES <= 0:
    raise ValueError('Wrong train dataset size {!r}'.format(
      experiment.task.train_data))
  if YT8M_VAL_EXAMPLES <= 0:
    raise ValueError('Wrong validation dataset size {!r}'.format(
      experiment.task.validation_data))
  experiment.task.train_data.global_batch_size = train_batch_size
  experiment.task.validation_data.global_batch_size = eval_batch_size
  steps_per_epoch = YT8M_TRAIN_EXAMPLES // train_batch_size
  experiment.trainer = cfg.TrainerConfig(
    steps_per_loop=steps_per_epoch,
    summary_interval=steps_per_epoch,
    checkpoint_interval=steps_per_epoch,
    train_steps=train_epochs * steps_per_epoch,
    validation_steps=YT8M_VAL_EXAMPLES //
                     eval_batch_size,
    validation_interval=steps_per_epoch,
    optimizer_config=optimization.OptimizationConfig({
      'optimizer': {
        'type': 'adam',
        'adam': {
        }
      },
      'learning_rate': {
        'type': 'exponential',
        'exponential': {
          'initial_learning_rate': learning_rate,
          'decay_rate': 0.95,
          'decay_steps': 4000000,
        }
      },
    }))
  return experiment

@exp_factory.register_config_factory('yt8m_experiment')
def yt8m_experiment() -> cfg.ExperimentConfig:
  """Video classification general."""
  exp_config = cfg.ExperimentConfig(
    runtime=cfg.RuntimeConfig(mixed_precision_dtype='bfloat16'),
    task=YT8MTask(),
    trainer=cfg.TrainerConfig(),
    restrictions=[
      'task.train_data.is_training != None',
      'task.validation_data.is_training != None',
      'task.train_data.num_classes == task.validation_data.num_classes',
      'task.train_data.feature_sizes != None',
      'task.train_data.feature_names != None',
    ])

  return add_trainer(exp_config, train_batch_size=1024,eval_batch_size=512)


