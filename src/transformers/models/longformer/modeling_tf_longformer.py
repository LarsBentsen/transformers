# coding=utf-8
# Copyright 2020 The Allen Institute for AI team and The HuggingFace Inc. team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Tensorflow Longformer model. """

import warnings
from dataclasses import dataclass
from typing import Optional, Tuple

import tensorflow as tf

from ...activations_tf import get_tf_activation
from ...file_utils import (
    MULTIPLE_CHOICE_DUMMY_INPUTS,
    ModelOutput,
    add_code_sample_docstrings,
    add_start_docstrings,
    add_start_docstrings_to_model_forward,
)
from ...modeling_tf_utils import (
    TFMaskedLanguageModelingLoss,
    TFMultipleChoiceLoss,
    TFPreTrainedModel,
    TFQuestionAnsweringLoss,
    TFSequenceClassificationLoss,
    TFTokenClassificationLoss,
    get_initializer,
    input_processing,
    keras_serializable,
    shape_list,
)
from ...utils import logging
from .configuration_longformer import LongformerConfig


logger = logging.get_logger(__name__)

_CHECKPOINT_FOR_DOC = "allenai/longformer-base-4096"
_CONFIG_FOR_DOC = "LongformerConfig"
_TOKENIZER_FOR_DOC = "LongformerTokenizer"

TF_LONGFORMER_PRETRAINED_MODEL_ARCHIVE_LIST = [
    "allenai/longformer-base-4096",
    "allenai/longformer-large-4096",
    "allenai/longformer-large-4096-finetuned-triviaqa",
    "allenai/longformer-base-4096-extra.pos.embd.only",
    "allenai/longformer-large-4096-extra.pos.embd.only",
    # See all Longformer models at https://huggingface.co/models?filter=longformer
]


@dataclass
class TFLongformerBaseModelOutput(ModelOutput):
    """
    Base class for Longformer's outputs, with potential hidden states, local and global attentions.

    Args:
        last_hidden_state (:obj:`tf.Tensor` of shape :obj:`(batch_size, sequence_length, hidden_size)`):
            Sequence of hidden-states at the output of the last layer of the model.
        hidden_states (:obj:`tuple(tf.Tensor)`, `optional`, returned when ``output_hidden_states=True`` is passed or when ``config.output_hidden_states=True``):
            Tuple of :obj:`tf.Tensor` (one for the output of the embeddings + one for the output of each layer) of
            shape :obj:`(batch_size, sequence_length, hidden_size)`.

            Hidden-states of the model at the output of each layer plus the initial embedding outputs.
        attentions (:obj:`tuple(tf.Tensor)`, `optional`, returned when ``output_attentions=True`` is passed or when ``config.output_attentions=True``):
            Tuple of :obj:`tf.Tensor` (one for each layer) of shape :obj:`(batch_size, num_heads, sequence_length, x +
            attention_window + 1)`, where ``x`` is the number of tokens with global attention mask.

            Local attentions weights after the attention softmax, used to compute the weighted average in the
            self-attention heads. Those are the attention weights from every token in the sequence to every token with
            global attention (first ``x`` values) and to every token in the attention window (remaining
            ``attention_window + 1`` values). Note that the first ``x`` values refer to tokens with fixed positions in
            the text, but the remaining ``attention_window + 1`` values refer to tokens with relative positions: the
            attention weight of a token to itself is located at index ``x + attention_window / 2`` and the
            ``attention_window / 2`` preceding (succeeding) values are the attention weights to the ``attention_window
            / 2`` preceding (succeeding) tokens. If the attention window contains a token with global attention, the
            attention weight at the corresponding index is set to 0; the value should be accessed from the first ``x``
            attention weights. If a token has global attention, the attention weights to all other tokens in
            :obj:`attentions` is set to 0, the values should be accessed from :obj:`global_attentions`.
        global_attentions (:obj:`tuple(tf.Tensor)`, `optional`, returned when ``output_attentions=True`` is passed or when ``config.output_attentions=True``):
            Tuple of :obj:`tf.Tensor` (one for each layer) of shape :obj:`(batch_size, num_heads, sequence_length, x)`,
            where ``x`` is the number of tokens with global attention mask.

            Global attentions weights after the attention softmax, used to compute the weighted average in the
            self-attention heads. Those are the attention weights from every token with global attention to every token
            in the sequence.
    """

    last_hidden_state: tf.Tensor = None
    hidden_states: Optional[Tuple[tf.Tensor]] = None
    attentions: Optional[Tuple[tf.Tensor]] = None
    global_attentions: Optional[Tuple[tf.Tensor]] = None


@dataclass
class TFLongformerBaseModelOutputWithPooling(ModelOutput):
    """
    Base class for Longformer's outputs that also contains a pooling of the last hidden states.

    Args:
        last_hidden_state (:obj:`tf.Tensor` of shape :obj:`(batch_size, sequence_length, hidden_size)`):
            Sequence of hidden-states at the output of the last layer of the model.
        pooler_output (:obj:`tf.Tensor` of shape :obj:`(batch_size, hidden_size)`):
            Last layer hidden-state of the first token of the sequence (classification token) further processed by a
            Linear layer and a Tanh activation function. The Linear layer weights are trained from the next sentence
            prediction (classification) objective during pretraining.
        hidden_states (:obj:`tuple(tf.Tensor)`, `optional`, returned when ``output_hidden_states=True`` is passed or when ``config.output_hidden_states=True``):
            Tuple of :obj:`tf.Tensor` (one for the output of the embeddings + one for the output of each layer) of
            shape :obj:`(batch_size, sequence_length, hidden_size)`.

            Hidden-states of the model at the output of each layer plus the initial embedding outputs.
        attentions (:obj:`tuple(tf.Tensor)`, `optional`, returned when ``output_attentions=True`` is passed or when ``config.output_attentions=True``):
            Tuple of :obj:`tf.Tensor` (one for each layer) of shape :obj:`(batch_size, num_heads, sequence_length, x +
            attention_window + 1)`, where ``x`` is the number of tokens with global attention mask.

            Local attentions weights after the attention softmax, used to compute the weighted average in the
            self-attention heads. Those are the attention weights from every token in the sequence to every token with
            global attention (first ``x`` values) and to every token in the attention window (remaining
            ``attention_window + 1`` values). Note that the first ``x`` values refer to tokens with fixed positions in
            the text, but the remaining ``attention_window + 1`` values refer to tokens with relative positions: the
            attention weight of a token to itself is located at index ``x + attention_window / 2`` and the
            ``attention_window / 2`` preceding (succeeding) values are the attention weights to the ``attention_window
            / 2`` preceding (succeeding) tokens. If the attention window contains a token with global attention, the
            attention weight at the corresponding index is set to 0; the value should be accessed from the first ``x``
            attention weights. If a token has global attention, the attention weights to all other tokens in
            :obj:`attentions` is set to 0, the values should be accessed from :obj:`global_attentions`.
        global_attentions (:obj:`tuple(tf.Tensor)`, `optional`, returned when ``output_attentions=True`` is passed or when ``config.output_attentions=True``):
            Tuple of :obj:`tf.Tensor` (one for each layer) of shape :obj:`(batch_size, num_heads, sequence_length, x)`,
            where ``x`` is the number of tokens with global attention mask.

            Global attentions weights after the attention softmax, used to compute the weighted average in the
            self-attention heads. Those are the attention weights from every token with global attention to every token
            in the sequence.
    """

    last_hidden_state: tf.Tensor = None
    pooler_output: tf.Tensor = None
    hidden_states: Optional[Tuple[tf.Tensor]] = None
    attentions: Optional[Tuple[tf.Tensor]] = None
    global_attentions: Optional[Tuple[tf.Tensor]] = None


@dataclass
class TFLongformerEncDecOutput(ModelOutput):
    """
    Base class for Longformer's outputs that also contains a pooling of the last hidden states.

    Args:
        last_hidden_state (:obj:`tf.Tensor` of shape :obj:`(batch_size, sequence_length, hidden_size)`):
            Sequence of hidden-states at the output of the last layer of the model.
        pooler_output (:obj:`tf.Tensor` of shape :obj:`(batch_size, hidden_size)`):
            Last layer hidden-state of the first token of the sequence (classification token) further processed by a
            Linear layer and a Tanh activation function. The Linear layer weights are trained from the next sentence
            prediction (classification) objective during pretraining.
        hidden_states (:obj:`tuple(tf.Tensor)`, `optional`, returned when ``output_hidden_states=True`` is passed or when ``config.output_hidden_states=True``):
            Tuple of :obj:`tf.Tensor` (one for the output of the embeddings + one for the output of each layer) of
            shape :obj:`(batch_size, sequence_length, hidden_size)`.

            Hidden-states of the model at the output of each layer plus the initial embedding outputs.
        attentions (:obj:`tuple(tf.Tensor)`, `optional`, returned when ``output_attentions=True`` is passed or when ``config.output_attentions=True``):
            Tuple of :obj:`tf.Tensor` (one for each layer) of shape :obj:`(batch_size, num_heads, sequence_length, x +
            attention_window + 1)`, where ``x`` is the number of tokens with global attention mask.

            Local attentions weights after the attention softmax, used to compute the weighted average in the
            self-attention heads. Those are the attention weights from every token in the sequence to every token with
            global attention (first ``x`` values) and to every token in the attention window (remaining
            ``attention_window + 1`` values). Note that the first ``x`` values refer to tokens with fixed positions in
            the text, but the remaining ``attention_window + 1`` values refer to tokens with relative positions: the
            attention weight of a token to itself is located at index ``x + attention_window / 2`` and the
            ``attention_window / 2`` preceding (succeeding) values are the attention weights to the ``attention_window
            / 2`` preceding (succeeding) tokens. If the attention window contains a token with global attention, the
            attention weight at the corresponding index is set to 0; the value should be accessed from the first ``x``
            attention weights. If a token has global attention, the attention weights to all other tokens in
            :obj:`attentions` is set to 0, the values should be accessed from :obj:`global_attentions`.
        global_attentions (:obj:`tuple(tf.Tensor)`, `optional`, returned when ``output_attentions=True`` is passed or when ``config.output_attentions=True``):
            Tuple of :obj:`tf.Tensor` (one for each layer) of shape :obj:`(batch_size, num_heads, sequence_length, x)`,
            where ``x`` is the number of tokens with global attention mask.

            Global attentions weights after the attention softmax, used to compute the weighted average in the
            self-attention heads. Those are the attention weights from every token with global attention to every token
            in the sequence.
    """

    last_hidden_state: tf.Tensor = None
    pooler_output: tf.Tensor = None
    hidden_states_dec: Optional[Tuple[tf.Tensor]] = None
    hidden_states_enc: Optional[Tuple[tf.Tensor]] = None
    attentions_dec: Optional[Tuple[tf.Tensor]] = None
    attentions_enc: Optional[Tuple[tf.Tensor]] = None
    global_attentions_dec: Optional[Tuple[tf.Tensor]] = None
    global_attentions_enc: Optional[Tuple[tf.Tensor]] = None



@dataclass
class TFLongformerMaskedLMOutput(ModelOutput):
    """
    Base class for masked language models outputs.

    Args:
        loss (:obj:`tf.Tensor` of shape :obj:`(1,)`, `optional`, returned when :obj:`labels` is provided):
            Masked language modeling (MLM) loss.
        logits (:obj:`tf.Tensor` of shape :obj:`(batch_size, sequence_length, config.vocab_size)`):
            Prediction scores of the language modeling head (scores for each vocabulary token before SoftMax).
        hidden_states (:obj:`tuple(tf.Tensor)`, `optional`, returned when ``output_hidden_states=True`` is passed or when ``config.output_hidden_states=True``):
            Tuple of :obj:`tf.Tensor` (one for the output of the embeddings + one for the output of each layer) of
            shape :obj:`(batch_size, sequence_length, hidden_size)`.

            Hidden-states of the model at the output of each layer plus the initial embedding outputs.
        attentions (:obj:`tuple(tf.Tensor)`, `optional`, returned when ``output_attentions=True`` is passed or when ``config.output_attentions=True``):
            Tuple of :obj:`tf.Tensor` (one for each layer) of shape :obj:`(batch_size, num_heads, sequence_length, x +
            attention_window + 1)`, where ``x`` is the number of tokens with global attention mask.

            Local attentions weights after the attention softmax, used to compute the weighted average in the
            self-attention heads. Those are the attention weights from every token in the sequence to every token with
            global attention (first ``x`` values) and to every token in the attention window (remaining
            ``attention_window + 1`` values). Note that the first ``x`` values refer to tokens with fixed positions in
            the text, but the remaining ``attention_window + 1`` values refer to tokens with relative positions: the
            attention weight of a token to itself is located at index ``x + attention_window / 2`` and the
            ``attention_window / 2`` preceding (succeeding) values are the attention weights to the ``attention_window
            / 2`` preceding (succeeding) tokens. If the attention window contains a token with global attention, the
            attention weight at the corresponding index is set to 0; the value should be accessed from the first ``x``
            attention weights. If a token has global attention, the attention weights to all other tokens in
            :obj:`attentions` is set to 0, the values should be accessed from :obj:`global_attentions`.
        global_attentions (:obj:`tuple(tf.Tensor)`, `optional`, returned when ``output_attentions=True`` is passed or when ``config.output_attentions=True``):
            Tuple of :obj:`tf.Tensor` (one for each layer) of shape :obj:`(batch_size, num_heads, sequence_length, x)`,
            where ``x`` is the number of tokens with global attention mask.

            Global attentions weights after the attention softmax, used to compute the weighted average in the
            self-attention heads. Those are the attention weights from every token with global attention to every token
            in the sequence.
    """

    loss: Optional[tf.Tensor] = None
    logits: tf.Tensor = None
    hidden_states: Optional[Tuple[tf.Tensor]] = None
    attentions: Optional[Tuple[tf.Tensor]] = None
    global_attentions: Optional[Tuple[tf.Tensor]] = None


@dataclass
class TFLongformerQuestionAnsweringModelOutput(ModelOutput):
    """
    Base class for outputs of question answering Longformer models.

    Args:
        loss (:obj:`tf.Tensor` of shape :obj:`(1,)`, `optional`, returned when :obj:`labels` is provided):
            Total span extraction loss is the sum of a Cross-Entropy for the start and end positions.
        start_logits (:obj:`tf.Tensor` of shape :obj:`(batch_size, sequence_length)`):
            Span-start scores (before SoftMax).
        end_logits (:obj:`tf.Tensor` of shape :obj:`(batch_size, sequence_length)`):
            Span-end scores (before SoftMax).
        hidden_states (:obj:`tuple(tf.Tensor)`, `optional`, returned when ``output_hidden_states=True`` is passed or when ``config.output_hidden_states=True``):
            Tuple of :obj:`tf.Tensor` (one for the output of the embeddings + one for the output of each layer) of
            shape :obj:`(batch_size, sequence_length, hidden_size)`.

            Hidden-states of the model at the output of each layer plus the initial embedding outputs.
        attentions (:obj:`tuple(tf.Tensor)`, `optional`, returned when ``output_attentions=True`` is passed or when ``config.output_attentions=True``):
            Tuple of :obj:`tf.Tensor` (one for each layer) of shape :obj:`(batch_size, num_heads, sequence_length, x +
            attention_window + 1)`, where ``x`` is the number of tokens with global attention mask.

            Local attentions weights after the attention softmax, used to compute the weighted average in the
            self-attention heads. Those are the attention weights from every token in the sequence to every token with
            global attention (first ``x`` values) and to every token in the attention window (remaining
            ``attention_window + 1`` values). Note that the first ``x`` values refer to tokens with fixed positions in
            the text, but the remaining ``attention_window + 1`` values refer to tokens with relative positions: the
            attention weight of a token to itself is located at index ``x + attention_window / 2`` and the
            ``attention_window / 2`` preceding (succeeding) values are the attention weights to the ``attention_window
            / 2`` preceding (succeeding) tokens. If the attention window contains a token with global attention, the
            attention weight at the corresponding index is set to 0; the value should be accessed from the first ``x``
            attention weights. If a token has global attention, the attention weights to all other tokens in
            :obj:`attentions` is set to 0, the values should be accessed from :obj:`global_attentions`.
        global_attentions (:obj:`tuple(tf.Tensor)`, `optional`, returned when ``output_attentions=True`` is passed or when ``config.output_attentions=True``):
            Tuple of :obj:`tf.Tensor` (one for each layer) of shape :obj:`(batch_size, num_heads, sequence_length, x)`,
            where ``x`` is the number of tokens with global attention mask.

            Global attentions weights after the attention softmax, used to compute the weighted average in the
            self-attention heads. Those are the attention weights from every token with global attention to every token
            in the sequence.
    """

    loss: Optional[tf.Tensor] = None
    start_logits: tf.Tensor = None
    end_logits: tf.Tensor = None
    hidden_states: Optional[Tuple[tf.Tensor]] = None
    attentions: Optional[Tuple[tf.Tensor]] = None
    global_attentions: Optional[Tuple[tf.Tensor]] = None


@dataclass
class TFLongformerSequenceClassifierOutput(ModelOutput):
    """
    Base class for outputs of sentence classification models.

    Args:
        loss (:obj:`tf.Tensor` of shape :obj:`(1,)`, `optional`, returned when :obj:`labels` is provided):
            Classification (or regression if config.num_labels==1) loss.
        logits (:obj:`tf.Tensor` of shape :obj:`(batch_size, config.num_labels)`):
            Classification (or regression if config.num_labels==1) scores (before SoftMax).
        hidden_states (:obj:`tuple(tf.Tensor)`, `optional`, returned when ``output_hidden_states=True`` is passed or when ``config.output_hidden_states=True``):
            Tuple of :obj:`tf.Tensor` (one for the output of the embeddings + one for the output of each layer) of
            shape :obj:`(batch_size, sequence_length, hidden_size)`.

            Hidden-states of the model at the output of each layer plus the initial embedding outputs.
        attentions (:obj:`tuple(tf.Tensor)`, `optional`, returned when ``output_attentions=True`` is passed or when ``config.output_attentions=True``):
            Tuple of :obj:`tf.Tensor` (one for each layer) of shape :obj:`(batch_size, num_heads, sequence_length, x +
            attention_window + 1)`, where ``x`` is the number of tokens with global attention mask.

            Local attentions weights after the attention softmax, used to compute the weighted average in the
            self-attention heads. Those are the attention weights from every token in the sequence to every token with
            global attention (first ``x`` values) and to every token in the attention window (remaining
            ``attention_window + 1`` values). Note that the first ``x`` values refer to tokens with fixed positions in
            the text, but the remaining ``attention_window + 1`` values refer to tokens with relative positions: the
            attention weight of a token to itself is located at index ``x + attention_window / 2`` and the
            ``attention_window / 2`` preceding (succeeding) values are the attention weights to the ``attention_window
            / 2`` preceding (succeeding) tokens. If the attention window contains a token with global attention, the
            attention weight at the corresponding index is set to 0; the value should be accessed from the first ``x``
            attention weights. If a token has global attention, the attention weights to all other tokens in
            :obj:`attentions` is set to 0, the values should be accessed from :obj:`global_attentions`.
        global_attentions (:obj:`tuple(tf.Tensor)`, `optional`, returned when ``output_attentions=True`` is passed or when ``config.output_attentions=True``):
            Tuple of :obj:`tf.Tensor` (one for each layer) of shape :obj:`(batch_size, num_heads, sequence_length, x)`,
            where ``x`` is the number of tokens with global attention mask.

            Global attentions weights after the attention softmax, used to compute the weighted average in the
            self-attention heads. Those are the attention weights from every token with global attention to every token
            in the sequence.
    """

    loss: Optional[tf.Tensor] = None
    logits: tf.Tensor = None
    hidden_states: Optional[Tuple[tf.Tensor]] = None
    attentions: Optional[Tuple[tf.Tensor]] = None
    global_attentions: Optional[Tuple[tf.Tensor]] = None


@dataclass
class TFLongformerMultipleChoiceModelOutput(ModelOutput):
    """
    Base class for outputs of multiple choice models.

    Args:
        loss (:obj:`tf.Tensor` of shape `(1,)`, `optional`, returned when :obj:`labels` is provided):
            Classification loss.
        logits (:obj:`tf.Tensor` of shape :obj:`(batch_size, num_choices)`):
            `num_choices` is the second dimension of the input tensors. (see `input_ids` above).

            Classification scores (before SoftMax).
        hidden_states (:obj:`tuple(tf.Tensor)`, `optional`, returned when ``output_hidden_states=True`` is passed or when ``config.output_hidden_states=True``):
            Tuple of :obj:`tf.Tensor` (one for the output of the embeddings + one for the output of each layer) of
            shape :obj:`(batch_size, sequence_length, hidden_size)`.

            Hidden-states of the model at the output of each layer plus the initial embedding outputs.
        attentions (:obj:`tuple(tf.Tensor)`, `optional`, returned when ``output_attentions=True`` is passed or when ``config.output_attentions=True``):
            Tuple of :obj:`tf.Tensor` (one for each layer) of shape :obj:`(batch_size, num_heads, sequence_length, x +
            attention_window + 1)`, where ``x`` is the number of tokens with global attention mask.

            Local attentions weights after the attention softmax, used to compute the weighted average in the
            self-attention heads. Those are the attention weights from every token in the sequence to every token with
            global attention (first ``x`` values) and to every token in the attention window (remaining
            ``attention_window + 1`` values). Note that the first ``x`` values refer to tokens with fixed positions in
            the text, but the remaining ``attention_window + 1`` values refer to tokens with relative positions: the
            attention weight of a token to itself is located at index ``x + attention_window / 2`` and the
            ``attention_window / 2`` preceding (succeeding) values are the attention weights to the ``attention_window
            / 2`` preceding (succeeding) tokens. If the attention window contains a token with global attention, the
            attention weight at the corresponding index is set to 0; the value should be accessed from the first ``x``
            attention weights. If a token has global attention, the attention weights to all other tokens in
            :obj:`attentions` is set to 0, the values should be accessed from :obj:`global_attentions`.
        global_attentions (:obj:`tuple(tf.Tensor)`, `optional`, returned when ``output_attentions=True`` is passed or when ``config.output_attentions=True``):
            Tuple of :obj:`tf.Tensor` (one for each layer) of shape :obj:`(batch_size, num_heads, sequence_length, x)`,
            where ``x`` is the number of tokens with global attention mask.

            Global attentions weights after the attention softmax, used to compute the weighted average in the
            self-attention heads. Those are the attention weights from every token with global attention to every token
            in the sequence.
    """

    loss: Optional[tf.Tensor] = None
    logits: tf.Tensor = None
    hidden_states: Optional[Tuple[tf.Tensor]] = None
    attentions: Optional[Tuple[tf.Tensor]] = None
    global_attentions: Optional[Tuple[tf.Tensor]] = None


@dataclass
class TFLongformerTokenClassifierOutput(ModelOutput):
    """
    Base class for outputs of token classification models.

    Args:
        loss (:obj:`tf.Tensor` of shape :obj:`(1,)`, `optional`, returned when ``labels`` is provided) :
            Classification loss.
        logits (:obj:`tf.Tensor` of shape :obj:`(batch_size, sequence_length, config.num_labels)`):
            Classification scores (before SoftMax).
        hidden_states (:obj:`tuple(tf.Tensor)`, `optional`, returned when ``output_hidden_states=True`` is passed or when ``config.output_hidden_states=True``):
            Tuple of :obj:`tf.Tensor` (one for the output of the embeddings + one for the output of each layer) of
            shape :obj:`(batch_size, sequence_length, hidden_size)`.

            Hidden-states of the model at the output of each layer plus the initial embedding outputs.
        attentions (:obj:`tuple(tf.Tensor)`, `optional`, returned when ``output_attentions=True`` is passed or when ``config.output_attentions=True``):
            Tuple of :obj:`tf.Tensor` (one for each layer) of shape :obj:`(batch_size, num_heads, sequence_length, x +
            attention_window + 1)`, where ``x`` is the number of tokens with global attention mask.

            Local attentions weights after the attention softmax, used to compute the weighted average in the
            self-attention heads. Those are the attention weights from every token in the sequence to every token with
            global attention (first ``x`` values) and to every token in the attention window (remaining
            ``attention_window + 1`` values). Note that the first ``x`` values refer to tokens with fixed positions in
            the text, but the remaining ``attention_window + 1`` values refer to tokens with relative positions: the
            attention weight of a token to itself is located at index ``x + attention_window / 2`` and the
            ``attention_window / 2`` preceding (succeeding) values are the attention weights to the ``attention_window
            / 2`` preceding (succeeding) tokens. If the attention window contains a token with global attention, the
            attention weight at the corresponding index is set to 0; the value should be accessed from the first ``x``
            attention weights. If a token has global attention, the attention weights to all other tokens in
            :obj:`attentions` is set to 0, the values should be accessed from :obj:`global_attentions`.
        global_attentions (:obj:`tuple(tf.Tensor)`, `optional`, returned when ``output_attentions=True`` is passed or when ``config.output_attentions=True``):
            Tuple of :obj:`tf.Tensor` (one for each layer) of shape :obj:`(batch_size, num_heads, sequence_length, x)`,
            where ``x`` is the number of tokens with global attention mask.

            Global attentions weights after the attention softmax, used to compute the weighted average in the
            self-attention heads. Those are the attention weights from every token with global attention to every token
            in the sequence.
    """

    loss: Optional[tf.Tensor] = None
    logits: tf.Tensor = None
    hidden_states: Optional[Tuple[tf.Tensor]] = None
    attentions: Optional[Tuple[tf.Tensor]] = None
    global_attentions: Optional[Tuple[tf.Tensor]] = None


def _compute_global_attention_mask(input_ids_shape, sep_token_indices, before_sep_token=True):
    """
    Computes global attention mask by putting attention on all tokens before `sep_token_id` if `before_sep_token is
    True` else after `sep_token_id`.
    """

    assert shape_list(sep_token_indices)[1] == 2, "`input_ids` should have two dimensions"
    question_end_index = tf.reshape(sep_token_indices, (input_ids_shape[0], 3, 2))[:, 0, 1][:, None]
    # bool attention mask with True in locations of global attention
    attention_mask = tf.expand_dims(tf.range(input_ids_shape[1]), axis=0)
    attention_mask = tf.tile(attention_mask, (input_ids_shape[0], 1))
    if before_sep_token is True:
        question_end_index = tf.tile(question_end_index, (1, input_ids_shape[1]))
        attention_mask = tf.cast(attention_mask < question_end_index, dtype=question_end_index.dtype)
    else:
        # last token is separation token and should not be counted and in the middle are two separation tokens
        question_end_index = tf.tile(question_end_index + 1, (1, input_ids_shape[1]))
        attention_mask = (
            tf.cast(
                attention_mask > question_end_index,
                dtype=question_end_index.dtype,
            )
            * tf.cast(attention_mask < input_ids_shape[-1], dtype=question_end_index.dtype)
        )

    return attention_mask


# Copied from transformers.models.roberta.modeling_tf_roberta.TFRobertaLMHead with Roberta->Longformer
class TFLongformerLMHead(tf.keras.layers.Layer):
    """Longformer Head for masked language modeling."""

    def __init__(self, config, input_embeddings, **kwargs):
        super().__init__(**kwargs)

        self.vocab_size = config.vocab_size
        self.hidden_size = config.hidden_size
        self.dense = tf.keras.layers.Dense(
            config.hidden_size, kernel_initializer=get_initializer(config.initializer_range), name="dense"
        )
        self.layer_norm = tf.keras.layers.LayerNormalization(epsilon=config.layer_norm_eps, name="layer_norm")
        self.act = get_tf_activation("gelu")

        # The output weights are the same as the input embeddings, but there is
        # an output-only bias for each token.
        self.decoder = input_embeddings

    def build(self, input_shape):
        self.bias = self.add_weight(shape=(self.vocab_size,), initializer="zeros", trainable=True, name="bias")

        super().build(input_shape)

    def get_output_embeddings(self):
        return self.decoder

    def set_output_embeddings(self, value):
        self.decoder.weight = value
        self.decoder.vocab_size = shape_list(value)[0]

    def get_bias(self):
        return {"bias": self.bias}

    def set_bias(self, value):
        self.bias = value["bias"]
        self.vocab_size = shape_list(value["bias"])[0]

    def call(self, hidden_states):
        hidden_states = self.dense(hidden_states)
        hidden_states = self.act(hidden_states)
        hidden_states = self.layer_norm(hidden_states)

        # project back to size of vocabulary with bias
        seq_length = shape_list(tensor=hidden_states)[1]
        hidden_states = tf.reshape(tensor=hidden_states, shape=[-1, self.hidden_size])
        hidden_states = tf.matmul(a=hidden_states, b=self.decoder.weight, transpose_b=True)
        hidden_states = tf.reshape(tensor=hidden_states, shape=[-1, seq_length, self.vocab_size])
        hidden_states = tf.nn.bias_add(value=hidden_states, bias=self.bias)

        return hidden_states


# Copied from transformers.models.roberta.modeling_tf_roberta.TFRobertaEmbeddings with Roberta->Longformer
class TFLongformerEmbeddings(tf.keras.layers.Layer):
    """
    Same as BertEmbeddings with a tiny tweak for positional embeddings indexing.
    """

    def __init__(self, config, **kwargs):
        super().__init__(**kwargs)

        self.padding_idx = 1
        self.vocab_size = config.vocab_size
        self.type_vocab_size = config.type_vocab_size
        self.hidden_size = config.hidden_size
        self.max_position_embeddings = config.max_position_embeddings
        self.initializer_range = config.initializer_range
        self.embeddings_sum = tf.keras.layers.Add()
        self.LayerNorm = tf.keras.layers.LayerNormalization(epsilon=config.layer_norm_eps, name="LayerNorm")
        self.dropout = tf.keras.layers.Dropout(rate=config.hidden_dropout_prob)

    def build(self, input_shape: tf.TensorShape):
        with tf.name_scope("word_embeddings"):
            self.weight = self.add_weight(
                name="weight",
                shape=[self.vocab_size, self.hidden_size],
                initializer=get_initializer(self.initializer_range),
            )

        with tf.name_scope("token_type_embeddings"):
            self.token_type_embeddings = self.add_weight(
                name="embeddings",
                shape=[self.type_vocab_size, self.hidden_size],
                initializer=get_initializer(self.initializer_range),
            )

        with tf.name_scope("position_embeddings"):
            self.position_embeddings = self.add_weight(
                name="embeddings",
                shape=[self.max_position_embeddings, self.hidden_size],
                initializer=get_initializer(self.initializer_range),
            )

        super().build(input_shape)

    def create_position_ids_from_input_ids(self, input_ids):
        """
        Replace non-padding symbols with their position numbers. Position numbers begin at padding_idx+1. Padding
        symbols are ignored. This is modified from fairseq's `utils.make_positions`.

        Args:
            input_ids: tf.Tensor
        Returns: tf.Tensor
        """
        mask = tf.cast(tf.math.not_equal(input_ids, self.padding_idx), dtype=input_ids.dtype)
        incremental_indices = tf.math.cumsum(mask, axis=1) * mask

        return incremental_indices + self.padding_idx

    def call(self, input_ids=None, position_ids=None, token_type_ids=None, inputs_embeds=None, training=False):
        """
        Applies embedding based on inputs tensor.

        Returns:
            final_embeddings (:obj:`tf.Tensor`): output embedding tensor.
        """
        assert not (input_ids is None and inputs_embeds is None)

        if input_ids is not None:
            inputs_embeds = tf.gather(params=self.weight, indices=input_ids)

        input_shape = shape_list(inputs_embeds)[:-1]

        if token_type_ids is None:
            token_type_ids = tf.fill(dims=input_shape, value=0)

        if position_ids is None:
            if input_ids is not None:
                # Create the position ids from the input token ids. Any padded tokens remain padded.
                position_ids = self.create_position_ids_from_input_ids(input_ids=input_ids)
            else:
                position_ids = tf.expand_dims(
                    tf.range(start=self.padding_idx + 1, limit=input_shape[-1] + self.padding_idx + 1), axis=0
                )
                position_ids = tf.tile(input=position_ids, multiples=(input_shape[0], 1))

        position_embeds = tf.gather(params=self.position_embeddings, indices=position_ids)
        token_type_embeds = tf.gather(params=self.token_type_embeddings, indices=token_type_ids)
        final_embeddings = self.embeddings_sum(inputs=[inputs_embeds, position_embeds, token_type_embeds])
        final_embeddings = self.LayerNorm(inputs=final_embeddings)
        final_embeddings = self.dropout(inputs=final_embeddings, training=training)

        return final_embeddings


# Copied from transformers.models.bert.modeling_tf_bert.TFBertIntermediate with Bert->Longformer
class TFLongformerIntermediate(tf.keras.layers.Layer):
    def __init__(self, config: LongformerConfig, **kwargs):
        super().__init__(**kwargs)

        self.dense = tf.keras.layers.Dense(
            units=config.intermediate_size, kernel_initializer=get_initializer(config.initializer_range), name="dense"
        )

        if isinstance(config.hidden_act, str):
            self.intermediate_act_fn = get_tf_activation(config.hidden_act)
        else:
            self.intermediate_act_fn = config.hidden_act

    def call(self, hidden_states: tf.Tensor) -> tf.Tensor:
        hidden_states = self.dense(inputs=hidden_states)
        hidden_states = self.intermediate_act_fn(hidden_states)

        return hidden_states


# Copied from transformers.models.bert.modeling_tf_bert.TFBertOutput with Bert->Longformer
class TFLongformerOutput(tf.keras.layers.Layer):
    def __init__(self, config: LongformerConfig, **kwargs):
        super().__init__(**kwargs)

        self.dense = tf.keras.layers.Dense(
            units=config.hidden_size, kernel_initializer=get_initializer(config.initializer_range), name="dense"
        )
        self.LayerNorm = tf.keras.layers.LayerNormalization(epsilon=config.layer_norm_eps, name="LayerNorm")
        self.dropout = tf.keras.layers.Dropout(rate=config.hidden_dropout_prob)

    def call(self, hidden_states: tf.Tensor, input_tensor: tf.Tensor, training: bool = False) -> tf.Tensor:
        hidden_states = self.dense(inputs=hidden_states)
        hidden_states = self.dropout(inputs=hidden_states, training=training)
        hidden_states = self.LayerNorm(inputs=hidden_states + input_tensor)

        return hidden_states


# Copied from transformers.models.bert.modeling_tf_bert.TFBertPooler with Bert->Longformer
class TFLongformerPooler(tf.keras.layers.Layer):
    def __init__(self, config: LongformerConfig, **kwargs):
        super().__init__(**kwargs)

        self.dense = tf.keras.layers.Dense(
            units=config.hidden_size,
            kernel_initializer=get_initializer(config.initializer_range),
            activation="tanh",
            name="dense",
        )

    def call(self, hidden_states: tf.Tensor) -> tf.Tensor:
        # We "pool" the model by simply taking the hidden state corresponding
        # to the first token.
        first_token_tensor = hidden_states[:, 0]
        pooled_output = self.dense(inputs=first_token_tensor)

        return pooled_output


# Copied from transformers.models.bert.modeling_tf_bert.TFBertSelfOutput with Bert->Longformer
class TFLongformerSelfOutput(tf.keras.layers.Layer):
    def __init__(self, config: LongformerConfig, **kwargs):
        super().__init__(**kwargs)

        self.dense = tf.keras.layers.Dense(
            units=config.hidden_size, kernel_initializer=get_initializer(config.initializer_range), name="dense"
        )
        self.LayerNorm = tf.keras.layers.LayerNormalization(epsilon=config.layer_norm_eps, name="LayerNorm")
        self.dropout = tf.keras.layers.Dropout(rate=config.hidden_dropout_prob)

    def call(self, hidden_states: tf.Tensor, input_tensor: tf.Tensor, training: bool = False) -> tf.Tensor:
        hidden_states = self.dense(inputs=hidden_states)
        hidden_states = self.dropout(inputs=hidden_states, training=training)
        hidden_states = self.LayerNorm(inputs=hidden_states + input_tensor)

        return hidden_states


class TFLongformerSelfAttention(tf.keras.layers.Layer):
    def __init__(self, config, layer_id, **kwargs):
        super().__init__(**kwargs)

        if config.hidden_size % config.num_attention_heads != 0:
            raise ValueError(
                f"The hidden size ({config.hidden_size}) is not a multiple of the number of attention "
                f"heads ({config.num_attention_heads}"
            )

        self.num_heads = config.num_attention_heads
        self.head_dim = int(config.hidden_size / config.num_attention_heads)
        self.embed_dim = config.hidden_size
        self.query = tf.keras.layers.Dense(
            self.embed_dim,
            kernel_initializer=get_initializer(config.initializer_range),
            name="query",
        )
        self.key = tf.keras.layers.Dense(
            self.embed_dim,
            kernel_initializer=get_initializer(config.initializer_range),
            name="key",
        )
        self.value = tf.keras.layers.Dense(
            self.embed_dim,
            kernel_initializer=get_initializer(config.initializer_range),
            name="value",
        )

        # separate projection layers for tokens with global attention
        self.query_global = tf.keras.layers.Dense(
            self.embed_dim,
            kernel_initializer=get_initializer(config.initializer_range),
            name="query_global",
        )
        self.key_global = tf.keras.layers.Dense(
            self.embed_dim,
            kernel_initializer=get_initializer(config.initializer_range),
            name="key_global",
        )
        self.value_global = tf.keras.layers.Dense(
            self.embed_dim,
            kernel_initializer=get_initializer(config.initializer_range),
            name="value_global",
        )
        self.dropout = tf.keras.layers.Dropout(config.attention_probs_dropout_prob)
        self.global_dropout = tf.keras.layers.Dropout(config.attention_probs_dropout_prob)
        self.layer_id = layer_id
        attention_window = config.attention_window[self.layer_id]

        assert (
            attention_window % 2 == 0
        ), f"`attention_window` for layer {self.layer_id} has to be an even value. Given {attention_window}"
        assert (
            attention_window > 0
        ), f"`attention_window` for layer {self.layer_id} has to be positive. Given {attention_window}"

        self.one_sided_attn_window_size = attention_window // 2

    def call(
        self,
        inputs,
        training=False,
    ):
        """
        LongformerSelfAttention expects `len(hidden_states)` to be multiple of `attention_window`. Padding to
        `attention_window` happens in LongformerModel.forward to avoid redoing the padding on each layer.

        The `attention_mask` is changed in :meth:`LongformerModel.forward` from 0, 1, 2 to:

            * -10000: no attention
            * 0: local attention
            * +10000: global attention
        """
        # retrieve input args
        (
            hidden_states,
            encoder_outputs,
            attention_mask,
            layer_head_mask,    #TODO: Feed in attention_mask1 as well...
            is_index_masked,
            is_index_global_attn,
            is_global_attn,
            is_look_ahead_mask,
            output_length
        ) = inputs

        # is_look_ahead_mask = True   # TODO: change approp
        # project hidden states
        if encoder_outputs is not None:
            key_vectors = self.key(encoder_outputs)
            value_vectors = self.value(encoder_outputs)
        else:
            key_vectors = self.key(hidden_states)
            value_vectors = self.value(hidden_states)
        batch_size, seq_len, embed_dim = shape_list(hidden_states)
        query_vectors = self.query(hidden_states)

        if tf.executing_eagerly():
            tf.debugging.assert_equal(
                embed_dim,
                self.embed_dim,
                message=f"hidden_states should have embed_dim = {self.embed_dim}, but has {embed_dim}",
            )

        # normalize query
        query_vectors /= tf.math.sqrt(tf.cast(self.head_dim, dtype=query_vectors.dtype))
        query_vectors = tf.reshape(query_vectors, (batch_size, seq_len, self.num_heads, self.head_dim))
        key_vectors = tf.reshape(key_vectors, (batch_size, seq_len, self.num_heads, self.head_dim))

        # attn_probs = (batch_size, seq_len, num_heads, window*2+1)
        attn_scores = self._sliding_chunks_query_key_matmul(
            query_vectors, key_vectors, self.one_sided_attn_window_size
        )

        # diagonal mask with zeros everywhere and -inf inplace of padding
        # TODO: Should be enough to feed the look-ahead mask here in the attention mask for decoder first attn
        diagonal_mask = self._sliding_chunks_query_key_matmul(
            tf.ones(shape_list(attention_mask)),
            attention_mask,
            self.one_sided_attn_window_size,
        )
        # if is_look_ahead_mask:
        #     look_ahead_mask = tf.concat([tf.zeros_like(diagonal_mask[:,:,:,:(self.one_sided_attn_window_size + 1)]),
        #                                  -10000*tf.ones_like(diagonal_mask[:,:,:,:self.one_sided_attn_window_size])],axis=-1)
        #     diagonal_mask += look_ahead_mask

        diagonal_mask = tf.cond(is_look_ahead_mask,
                                lambda: diagonal_mask + tf.concat(
                                    [tf.zeros_like(diagonal_mask[:, :, :, :(self.one_sided_attn_window_size + 1)]),
                                     -10000 * tf.ones_like(diagonal_mask[:, :, :, :self.one_sided_attn_window_size])],
                                    axis=-1),
                                lambda: diagonal_mask)

        # pad local attention probs
        attn_scores += diagonal_mask

        if tf.executing_eagerly():
            tf.debugging.assert_equal(
                shape_list(attn_scores),
                [batch_size, seq_len, self.num_heads, self.one_sided_attn_window_size * 2 + 1],
                message=f"attn_probs should be of size ({batch_size}, {seq_len}, {self.num_heads}, {self.one_sided_attn_window_size * 2 + 1}), but is of size {shape_list(attn_scores)}",
            )

        # compute global attn indices required through out forward fn
        (
            max_num_global_attn_indices,
            is_index_global_attn_nonzero,
            is_local_index_global_attn_nonzero,
            is_local_index_no_global_attn_nonzero,
        ) = self._get_global_attn_indices(is_index_global_attn)

        # this function is only relevant for global attention
        attn_scores = tf.cond(
            is_global_attn,
            lambda: self._concat_with_global_key_attn_probs(
                attn_scores=attn_scores,
                query_vectors=query_vectors,
                key_vectors=key_vectors,
                max_num_global_attn_indices=max_num_global_attn_indices,
                is_index_global_attn_nonzero=is_index_global_attn_nonzero,
                is_local_index_global_attn_nonzero=is_local_index_global_attn_nonzero,
                is_local_index_no_global_attn_nonzero=is_local_index_no_global_attn_nonzero,
                is_look_ahead_mask=is_look_ahead_mask  # TODO Sort properly
            ),
            lambda: attn_scores,
        )
        # TODO check actual full global attention stuff (where is this done??)
        attn_probs = tf.nn.softmax(attn_scores, axis=-1)    # TODO: Check that attention is masked correctly for global

        # softmax sometimes inserts NaN if all positions are masked, replace them with 0
        # Make sure to create a mask with the proper shape:
        # if is_global_attn==True => [batch_size, seq_len, self.num_heads, self.one_sided_attn_window_size * 2 + max_num_global_attn_indices + 1]
        # if is_global_attn==False => [batch_size, seq_len, self.num_heads, self.one_sided_attn_window_size * 2 + 1]
        masked_index = tf.cond(
            is_global_attn,
            lambda: tf.tile(
                is_index_masked[:, :, None, None],
                (1, 1, self.num_heads, self.one_sided_attn_window_size * 2 + max_num_global_attn_indices + 1),
            ),
            lambda: tf.tile(
                is_index_masked[:, :, None, None],
                (1, 1, self.num_heads, self.one_sided_attn_window_size * 2 + 1),
            ),
        )
        attn_probs = tf.where(
            masked_index,
            tf.zeros(shape_list(masked_index), dtype=attn_probs.dtype),
            attn_probs,
        )

        if layer_head_mask is not None:
            if tf.executing_eagerly():
                tf.debugging.assert_equal(
                    shape_list(layer_head_mask),
                    [self.num_heads],
                    message=f"Head mask for a single layer should be of size {(self.num_heads)}, but is {shape_list(layer_head_mask)}",
                )

            attn_probs = tf.reshape(layer_head_mask, (1, 1, -1, 1)) * attn_probs

        # apply dropout
        attn_probs = self.dropout(attn_probs, training=training)
        value_vectors = tf.reshape(value_vectors, (batch_size, seq_len, self.num_heads, self.head_dim))

        # if global attention, compute sum of global and local attn
        attn_output = tf.cond(
            is_global_attn,
            lambda: self._compute_attn_output_with_global_indices(
                value_vectors=value_vectors,
                attn_probs=attn_probs,
                max_num_global_attn_indices=max_num_global_attn_indices,
                is_index_global_attn_nonzero=is_index_global_attn_nonzero,
                is_local_index_global_attn_nonzero=is_local_index_global_attn_nonzero,
            ),
            lambda: self._sliding_chunks_matmul_attn_probs_value(
                attn_probs, value_vectors, self.one_sided_attn_window_size
            ),
        )

        if tf.executing_eagerly():
            tf.debugging.assert_equal(
                shape_list(attn_output),
                [batch_size, seq_len, self.num_heads, self.head_dim],
                message="Unexpected size",
            )

        attn_output = tf.reshape(attn_output, (batch_size, seq_len, embed_dim))

        # compute value for global attention and overwrite to attention output
        # TODO: remove the redundant computation
        attn_output, global_attn_probs = tf.cond(
            is_global_attn,
            lambda: self._compute_global_attn_output_from_hidden(
                attn_output=attn_output,
                hidden_states=hidden_states,    # TODO Change
                max_num_global_attn_indices=max_num_global_attn_indices,
                layer_head_mask=layer_head_mask,
                is_local_index_global_attn_nonzero=is_local_index_global_attn_nonzero,
                is_index_global_attn_nonzero=is_index_global_attn_nonzero,
                is_local_index_no_global_attn_nonzero=is_local_index_no_global_attn_nonzero,
                is_index_masked=is_index_masked,
                training=training,
                is_look_ahead_mask=is_look_ahead_mask,
                encoder_outputs=encoder_outputs,
            ),
            lambda: (attn_output, tf.zeros((batch_size, self.num_heads, max_num_global_attn_indices, seq_len))),
        )

        # make sure that local attention probabilities are set to 0 for indices of global attn
        # Make sure to create a mask with the proper shape:
        # if is_global_attn==True => [batch_size, seq_len, self.num_heads, self.one_sided_attn_window_size * 2 + max_num_global_attn_indices + 1]
        # if is_global_attn==False => [batch_size, seq_len, self.num_heads, self.one_sided_attn_window_size * 2 + 1]
        masked_global_attn_index = tf.cond(
            is_global_attn,
            lambda: tf.tile(
                is_index_global_attn[:, :, None, None],
                (1, 1, self.num_heads, self.one_sided_attn_window_size * 2 + max_num_global_attn_indices + 1),
            ),
            lambda: tf.tile(
                is_index_global_attn[:, :, None, None],
                (1, 1, self.num_heads, self.one_sided_attn_window_size * 2 + 1),
            ),
        )

        attn_probs = tf.where(
            masked_global_attn_index,
            tf.zeros(shape_list(masked_global_attn_index), dtype=attn_probs.dtype),
            attn_probs,
        )

        if output_length is not None:
            # if tf.cast(output_length, is_index_global_attn_nonzero.dtype) < tf.reduce_max(is_index_global_attn_nonzero[:,1]) + 1:
            #     attn_output = (tf.concat([tf.ones((batch_size, output_length, embed_dim)), tf.zeros((batch_size, seq_len - output_length, embed_dim))], axis=1)*attn_output)
            #     num_remove = tf.reduce_sum(tf.cast((tf.cast(output_length, is_index_global_attn_nonzero.dtype) < tf.unique(is_index_global_attn_nonzero[:,1])[0] + 1), 'int32'))
            #     global_attn_probs = global_attn_probs[:, :, :-num_remove, :]

            def trim_output(batch_size,
                            output_length,
                            embed_dim,
                            seq_len,
                            attn_output,
                            is_index_global_attn_nonzero,
                            global_attn_probs):
                attn_output = (tf.concat([tf.ones((batch_size, output_length, embed_dim)),
                                          tf.zeros((batch_size, seq_len - output_length, embed_dim))],
                                         axis=1) * attn_output)
                num_remove = tf.reduce_sum(tf.cast((tf.cast(output_length, is_index_global_attn_nonzero.dtype) <
                                                    tf.unique(is_index_global_attn_nonzero[:, 1])[0] + 1), 'int32'))
                global_attn_probs = global_attn_probs[:, :, :-num_remove, :]

                return attn_output, global_attn_probs

            attn_output, global_attn_probs = tf.cond(
                tf.cast(output_length, is_index_global_attn_nonzero.dtype) < tf.reduce_max(is_index_global_attn_nonzero[:,1]) + 1,
                lambda: trim_output(batch_size,
                                    output_length,
                                    embed_dim,
                                    seq_len,
                                    attn_output,
                                    is_index_global_attn_nonzero,
                                    global_attn_probs),
                lambda: (attn_output, global_attn_probs)
            )

        outputs = (attn_output, attn_probs, global_attn_probs)

        # attn_probs:
        # For three global indices and a window length of 4:
        # Note that if the the particular window indices is a global indices --> then 0.
        # If winodow is outside of data range (i.e. wind_-2 and wind_-1 for the first entry) --> 0
        # [glob_1, glob_2, glob_3, window_-2, window_-1, self, wind_+1, wind_+2]

        return outputs

    def _sliding_chunks_query_key_matmul(self, query, key, window_overlap):
        """
        Matrix multiplication of query and key tensors using with a sliding window attention pattern. This
        implementation splits the input into overlapping chunks of size 2w (e.g. 512 for pretrained Longformer) with an
        overlap of size window_overlap
        See: https://github.com/allenai/longformer/issues/157 for some intuition about the reordering.
        Computes the chunkes (coloured) and the trims it as this is more efficient on GPUs than loop implementation...
        """
        batch_size, seq_len, num_heads, head_dim = shape_list(query)

        if tf.executing_eagerly():
            tf.debugging.assert_equal(
                seq_len % (window_overlap * 2),
                0,
                message=f"Sequence length should be multiple of {window_overlap * 2}. Given {seq_len}",
            )
            tf.debugging.assert_equal(
                shape_list(query),
                shape_list(key),
                message=f"Shape of query and key should be equal, but got query: {shape_list(query)} and key: {shape_list(key)}",
            )

        chunks_count = seq_len // window_overlap - 1

        # group batch_size and num_heads dimensions into one, then chunk seq_len into chunks of size window_overlap * 2
        query = tf.reshape(
            tf.transpose(query, (0, 2, 1, 3)),
            (batch_size * num_heads, seq_len, head_dim),
        )
        key = tf.reshape(tf.transpose(key, (0, 2, 1, 3)), (batch_size * num_heads, seq_len, head_dim))
        chunked_query = self._chunk(query, window_overlap)
        chunked_key = self._chunk(key, window_overlap)

        # matrix multiplication
        # bcxd: batch_size * num_heads x chunks x 2window_overlap x head_dim
        # bcyd: batch_size * num_heads x chunks x 2window_overlap x head_dim
        # bcxy: batch_size * num_heads x chunks x 2window_overlap x 2window_overlap
        chunked_query = tf.cast(chunked_query, dtype=chunked_key.dtype)
        chunked_attention_scores = tf.einsum("bcxd,bcyd->bcxy", chunked_query, chunked_key)  # multiply

        # convert diagonals into columns
        paddings = tf.convert_to_tensor([[0, 0], [0, 0], [0, 1], [0, 0]])
        diagonal_chunked_attention_scores = self._pad_and_transpose_last_two_dims(chunked_attention_scores, paddings)

        # allocate space for the overall attention matrix where the chunks are combined. The last dimension
        # has (window_overlap * 2 + 1) columns. The first (window_overlap) columns are the window_overlap lower triangles (attention from a word to
        # window_overlap previous words). The following column is attention score from each word to itself, then
        # followed by window_overlap columns for the upper triangle.

        # copy parts from diagonal_chunked_attention_scores into the combined matrix of attentions
        # - copying the main diagonal and the upper triangle
        # TODO: This code is most likely not very efficient and should be improved
        diagonal_attn_scores_up_triang = tf.concat(
            [
                diagonal_chunked_attention_scores[:, :, :window_overlap, : window_overlap + 1],
                diagonal_chunked_attention_scores[:, -1:, window_overlap:, : window_overlap + 1],
            ],
            axis=1,
        )

        # - copying the lower triangle
        diagonal_attn_scores_low_triang = tf.concat(
            [
                tf.zeros(
                    (batch_size * num_heads, 1, window_overlap, window_overlap),
                    dtype=diagonal_chunked_attention_scores.dtype,
                ),
                diagonal_chunked_attention_scores[:, :, -(window_overlap + 1) : -1, window_overlap + 1 :],
            ],
            axis=1,
        )
        diagonal_attn_scores_first_chunk = tf.concat(
            [
                tf.roll(
                    diagonal_chunked_attention_scores,
                    shift=[1, window_overlap],
                    axis=[2, 3],
                )[:, :, :window_overlap, :window_overlap],
                tf.zeros(
                    (batch_size * num_heads, 1, window_overlap, window_overlap),
                    dtype=diagonal_chunked_attention_scores.dtype,
                ),
            ],
            axis=1,
        )
        first_chunk_mask = (
            tf.tile(
                tf.range(chunks_count + 1)[None, :, None, None],
                (batch_size * num_heads, 1, window_overlap, window_overlap),
            )
            < 1
        )
        diagonal_attn_scores_low_triang = tf.where(
            first_chunk_mask,
            diagonal_attn_scores_first_chunk,
            diagonal_attn_scores_low_triang,
        )

        # merging upper and lower triangle
        diagonal_attention_scores = tf.concat(
            [diagonal_attn_scores_low_triang, diagonal_attn_scores_up_triang], axis=-1
        )

        # separate batch_size and num_heads dimensions again
        diagonal_attention_scores = tf.transpose(
            tf.reshape(
                diagonal_attention_scores,
                (batch_size, num_heads, seq_len, 2 * window_overlap + 1),
            ),
            (0, 2, 1, 3),
        )

        diagonal_attention_scores = self._mask_invalid_locations(diagonal_attention_scores, window_overlap)

        return diagonal_attention_scores

    @staticmethod
    def _mask_invalid_locations(input_tensor, window_overlap):
        # create correct upper triangle bool mask
        mask_2d_upper = tf.reverse(
            tf.linalg.band_part(tf.ones(shape=(window_overlap, window_overlap + 1)), -1, 0),
            axis=[0],
        )

        # pad to full matrix
        padding = tf.convert_to_tensor(
            [[0, shape_list(input_tensor)[1] - window_overlap], [0, shape_list(input_tensor)[3] - window_overlap - 1]]
        )

        # create lower mask
        mask_2d = tf.pad(mask_2d_upper, padding)

        # combine with upper mask
        mask_2d = mask_2d + tf.reverse(mask_2d, axis=[0, 1])

        # broadcast to full matrix
        mask_4d = tf.tile(mask_2d[None, :, None, :], (shape_list(input_tensor)[0], 1, 1, 1))

        # inf tensor used for masking
        inf_tensor = -float("inf") * tf.ones_like(input_tensor)

        # mask
        input_tensor = tf.where(tf.math.greater(mask_4d, 0), inf_tensor, input_tensor)

        return input_tensor

    def _sliding_chunks_matmul_attn_probs_value(self, attn_probs, value, window_overlap):
        """
        Same as _sliding_chunks_query_key_matmul but for attn_probs and value tensors. Returned tensor will be of the
        same shape as `attn_probs`
        """

        batch_size, seq_len, num_heads, head_dim = shape_list(value)

        if tf.executing_eagerly():
            tf.debugging.assert_equal(
                seq_len % (window_overlap * 2),
                0,
                message="Seq_len has to be multiple of 2 * window_overlap",
            )
            tf.debugging.assert_equal(
                shape_list(attn_probs)[:3],
                shape_list(value)[:3],
                message="value and attn_probs must have same dims (except head_dim)",
            )
            tf.debugging.assert_equal(
                shape_list(attn_probs)[3],
                2 * window_overlap + 1,
                message="attn_probs last dim has to be 2 * window_overlap + 1",
            )

        chunks_count = seq_len // window_overlap - 1

        # group batch_size and num_heads dimensions into one, then chunk seq_len into chunks of size 2 window overlap
        chunked_attn_probs = tf.reshape(
            tf.transpose(attn_probs, (0, 2, 1, 3)),
            (
                batch_size * num_heads,
                seq_len // window_overlap,
                window_overlap,
                2 * window_overlap + 1,
            ),
        )

        # group batch_size and num_heads dimensions into one
        value = tf.reshape(
            tf.transpose(value, (0, 2, 1, 3)),
            (batch_size * num_heads, seq_len, head_dim),
        )

        # pad seq_len with w at the beginning of the sequence and another window overlap at the end
        paddings = tf.convert_to_tensor([[0, 0], [window_overlap, window_overlap], [0, 0]])
        padded_value = tf.pad(value, paddings, constant_values=-1)

        # chunk padded_value into chunks of size 3 window overlap and an overlap of size window overlap
        frame_size = 3 * window_overlap * head_dim
        frame_hop_size = (shape_list(padded_value)[1] * head_dim - frame_size) // chunks_count
        chunked_value = tf.signal.frame(
            tf.reshape(padded_value, (batch_size * num_heads, -1)),
            frame_size,
            frame_hop_size,
        )
        chunked_value = tf.reshape(
            chunked_value,
            (batch_size * num_heads, chunks_count + 1, 3 * window_overlap, head_dim),
        )

        if tf.executing_eagerly():
            tf.debugging.assert_equal(
                shape_list(chunked_value),
                [batch_size * num_heads, chunks_count + 1, 3 * window_overlap, head_dim],
                message="Chunked value has the wrong shape",
            )

        chunked_attn_probs = self._pad_and_diagonalize(chunked_attn_probs)
        context = tf.einsum("bcwd,bcdh->bcwh", chunked_attn_probs, chunked_value)
        context = tf.transpose(
            tf.reshape(context, (batch_size, num_heads, seq_len, head_dim)),
            (0, 2, 1, 3),
        )

        return context

    @staticmethod
    def _pad_and_transpose_last_two_dims(hidden_states_padded, paddings):
        """pads rows and then flips rows and columns"""
        hidden_states_padded = tf.pad(
            hidden_states_padded, paddings
        )  # padding value is not important because it will be overwritten
        batch_size, chunk_size, seq_length, hidden_dim = shape_list(hidden_states_padded)
        hidden_states_padded = tf.reshape(hidden_states_padded, (batch_size, chunk_size, hidden_dim, seq_length))

        return hidden_states_padded

    @staticmethod
    def _pad_and_diagonalize(chunked_hidden_states):
        """
        shift every row 1 step right, converting columns into diagonals.

        Example::

              chunked_hidden_states: [ 0.4983,  2.6918, -0.0071,  1.0492,
                                       -1.8348,  0.7672,  0.2986,  0.0285,
                                       -0.7584,  0.4206, -0.0405,  0.1599,
                                       2.0514, -1.1600,  0.5372,  0.2629 ]
              window_overlap = num_rows = 4
             (pad & diagonalize) =>
             [ 0.4983,  2.6918, -0.0071,  1.0492, 0.0000,  0.0000,  0.0000
               0.0000,  -1.8348,  0.7672,  0.2986,  0.0285, 0.0000,  0.0000
               0.0000,  0.0000, -0.7584,  0.4206, -0.0405,  0.1599, 0.0000
               0.0000,  0.0000,  0.0000, 2.0514, -1.1600,  0.5372,  0.2629 ]
        """
        total_num_heads, num_chunks, window_overlap, hidden_dim = shape_list(chunked_hidden_states)
        paddings = tf.convert_to_tensor([[0, 0], [0, 0], [0, 0], [0, window_overlap + 1]])
        chunked_hidden_states = tf.pad(
            chunked_hidden_states, paddings
        )  # total_num_heads x num_chunks x window_overlap x (hidden_dim+window_overlap+1). Padding value is not important because it'll be overwritten
        chunked_hidden_states = tf.reshape(
            chunked_hidden_states, (total_num_heads, num_chunks, -1)
        )  # total_num_heads x num_chunks x window_overlapL+window_overlapwindow_overlap+window_overlap
        chunked_hidden_states = chunked_hidden_states[
            :, :, :-window_overlap
        ]  # total_num_heads x num_chunks x window_overlapL+window_overlapwindow_overlap
        chunked_hidden_states = tf.reshape(
            chunked_hidden_states,
            (total_num_heads, num_chunks, window_overlap, window_overlap + hidden_dim),
        )  # total_num_heads x num_chunks, window_overlap x hidden_dim+window_overlap
        chunked_hidden_states = chunked_hidden_states[:, :, :, :-1]

        return chunked_hidden_states

    @staticmethod
    def _chunk(hidden_states, window_overlap):
        """convert into overlapping chunks. Chunk size = 2w, overlap size = w"""
        batch_size, seq_length, hidden_dim = shape_list(hidden_states)
        num_output_chunks = 2 * (seq_length // (2 * window_overlap)) - 1

        # define frame size and frame stride (similar to convolution)
        frame_hop_size = window_overlap * hidden_dim
        frame_size = 2 * frame_hop_size
        hidden_states = tf.reshape(hidden_states, (batch_size, seq_length * hidden_dim))

        # chunk with overlap
        chunked_hidden_states = tf.signal.frame(hidden_states, frame_size, frame_hop_size)

        if tf.executing_eagerly():
            tf.debugging.assert_equal(
                shape_list(chunked_hidden_states),
                [batch_size, num_output_chunks, frame_size],
                message=f"Make sure chunking is correctly applied. `Chunked hidden states should have output  dimension {[batch_size, frame_size, num_output_chunks]}, but got {shape_list(chunked_hidden_states)}.",
            )

        chunked_hidden_states = tf.reshape(
            chunked_hidden_states,
            (batch_size, num_output_chunks, 2 * window_overlap, hidden_dim),
        )

        return chunked_hidden_states

    @staticmethod
    def _get_global_attn_indices(is_index_global_attn):
        """compute global attn indices required throughout forward pass"""
        # helper variable
        num_global_attn_indices = tf.math.count_nonzero(is_index_global_attn, axis=1)
        num_global_attn_indices = tf.cast(num_global_attn_indices, dtype=tf.constant(1).dtype)

        # max number of global attn indices in batch
        max_num_global_attn_indices = tf.reduce_max(num_global_attn_indices)

        # indices of global attn
        is_index_global_attn_nonzero = tf.where(is_index_global_attn)

        # helper variable
        is_local_index_global_attn = tf.range(max_num_global_attn_indices) < tf.expand_dims(
            num_global_attn_indices, axis=-1
        )

        # location of the non-padding values within global attention indices
        is_local_index_global_attn_nonzero = tf.where(is_local_index_global_attn)

        # location of the padding values within global attention indices
        is_local_index_no_global_attn_nonzero = tf.where(tf.math.logical_not(is_local_index_global_attn))

        return (
            max_num_global_attn_indices,
            is_index_global_attn_nonzero,
            is_local_index_global_attn_nonzero,
            is_local_index_no_global_attn_nonzero,
        )

    def _concat_with_global_key_attn_probs(
        self,
        attn_scores,
        key_vectors,
        query_vectors,
        max_num_global_attn_indices,
        is_index_global_attn_nonzero,
        is_local_index_global_attn_nonzero,
        is_local_index_no_global_attn_nonzero,
        is_look_ahead_mask=False
    ):
        batch_size = shape_list(key_vectors)[0]

        # select global key vectors
        global_key_vectors = tf.gather_nd(key_vectors, is_index_global_attn_nonzero)

        # create only global key vectors
        key_vectors_only_global = tf.scatter_nd(
            is_local_index_global_attn_nonzero,
            global_key_vectors,
            shape=(
                batch_size,
                max_num_global_attn_indices,
                self.num_heads,
                self.head_dim,
            ),
        )

        # (batch_size, seq_len, num_heads, max_num_global_attn_indices)
        attn_probs_from_global_key = tf.einsum("blhd,bshd->blhs", query_vectors, key_vectors_only_global)

        # (batch_size, max_num_global_attn_indices, seq_len, num_heads)
        attn_probs_from_global_key_trans = tf.transpose(attn_probs_from_global_key, (0, 3, 1, 2))
        mask_shape = (shape_list(is_local_index_no_global_attn_nonzero)[0],) + tuple(
            shape_list(attn_probs_from_global_key_trans)[-2:]
        )
        mask = tf.ones(mask_shape) * -10000.0
        mask = tf.cast(mask, dtype=attn_probs_from_global_key_trans.dtype)

        # scatter mask
        attn_probs_from_global_key_trans = tf.tensor_scatter_nd_update(
            attn_probs_from_global_key_trans,
            is_local_index_no_global_attn_nonzero,
            mask,
        )

        # (batch_size, seq_len, num_heads, max_num_global_attn_indices)
        attn_probs_from_global_key = tf.transpose(attn_probs_from_global_key_trans, (0, 2, 3, 1))

        # if is_look_ahead_mask:
        #     shape_attn = tf.shape(attn_probs_from_global_key)
        #     look_ahead_mask = tf.reshape(
        #         tf.tile(tf.repeat(tf.range(tf.shape(attn_probs_from_global_key)[1]), tf.reduce_prod(shape_attn[2:])),
        #                 [tf.reduce_prod(shape_attn[0])]), shape_attn)
        #     look_ahead_mask = tf.cast(look_ahead_mask, is_index_global_attn_nonzero.dtype)
        #
        #     # NOTE: Assume same global attention indices for all samples in a batch...
        #     #         global_attn_scores = tf.where(attn_mask, -10000.0, global_attn_scores)
        #     look_ahead_mask = look_ahead_mask < is_index_global_attn_nonzero[:max_num_global_attn_indices, 1]
        #
        #     attn_probs_from_global_key = tf.where(look_ahead_mask, -10000., attn_probs_from_global_key)

        def look_ahead_func(attn_probs_from_global_key,
                            is_index_global_attn_nonzero,
                            max_num_global_attn_indices):
            shape_attn = tf.shape(attn_probs_from_global_key)
            look_ahead_mask = tf.reshape(
                tf.tile(tf.repeat(tf.range(tf.shape(attn_probs_from_global_key)[1]), tf.reduce_prod(shape_attn[2:])),
                        [tf.reduce_prod(shape_attn[0])]), shape_attn)
            look_ahead_mask = tf.cast(look_ahead_mask, is_index_global_attn_nonzero.dtype)

            # NOTE: Assume same global attention indices for all samples in a batch...
            #         global_attn_scores = tf.where(attn_mask, -10000.0, global_attn_scores)
            look_ahead_mask = look_ahead_mask < is_index_global_attn_nonzero[:max_num_global_attn_indices, 1]

            attn_probs_from_global_key = tf.where(look_ahead_mask, -10000., attn_probs_from_global_key)

            return attn_probs_from_global_key

        attn_probs_from_global_key = tf.cond(
            is_look_ahead_mask,
            lambda: look_ahead_func(attn_probs_from_global_key,
                                    is_index_global_attn_nonzero,
                                    max_num_global_attn_indices),
            lambda: attn_probs_from_global_key)

        # concat to attn_probs
        # (batch_size, seq_len, num_heads, extra attention count + 2*window+1)
        attn_scores = tf.concat((attn_probs_from_global_key, attn_scores), axis=-1)

        return attn_scores

    def _compute_attn_output_with_global_indices(
        self,
        value_vectors,
        attn_probs,
        max_num_global_attn_indices,
        is_index_global_attn_nonzero,
        is_local_index_global_attn_nonzero,
    ):
        batch_size = shape_list(attn_probs)[0]

        # cut local attn probs to global only
        attn_probs_only_global = attn_probs[:, :, :, :max_num_global_attn_indices]

        # select global value vectors
        global_value_vectors = tf.gather_nd(value_vectors, is_index_global_attn_nonzero)

        # create only global value vectors
        value_vectors_only_global = tf.scatter_nd(
            is_local_index_global_attn_nonzero,
            global_value_vectors,
            shape=(
                batch_size,
                max_num_global_attn_indices,
                self.num_heads,
                self.head_dim,
            ),
        )

        # compute attn output only global
        attn_output_only_global = tf.einsum("blhs,bshd->blhd", attn_probs_only_global, value_vectors_only_global)

        # reshape attn probs
        attn_probs_without_global = attn_probs[:, :, :, max_num_global_attn_indices:]

        # compute attn output without global
        attn_output_without_global = self._sliding_chunks_matmul_attn_probs_value(
            attn_probs_without_global, value_vectors, self.one_sided_attn_window_size
        )

        return attn_output_only_global + attn_output_without_global

    def _compute_global_attn_output_from_hidden(
        self,
        attn_output,
        hidden_states,
        max_num_global_attn_indices,
        layer_head_mask,
        is_local_index_global_attn_nonzero,
        is_index_global_attn_nonzero,
        is_local_index_no_global_attn_nonzero,
        is_index_masked,
        training,
        is_look_ahead_mask=False,
        encoder_outputs=None
    ):
        batch_size, seq_len = shape_list(hidden_states)[:2]

        # prepare global hidden states
        global_attn_hidden_states = tf.gather_nd(hidden_states, is_index_global_attn_nonzero)
        global_attn_hidden_states = tf.scatter_nd(
            is_local_index_global_attn_nonzero,
            global_attn_hidden_states,
            shape=(batch_size, max_num_global_attn_indices, self.embed_dim),
        )

        # global key, query, value
        global_query_vectors_only_global = self.query_global(global_attn_hidden_states)
        if encoder_outputs is not None:
            global_key_vectors = self.key_global(encoder_outputs)
            global_value_vectors = self.value_global(encoder_outputs)
        else:
            global_key_vectors = self.key_global(hidden_states)
            global_value_vectors = self.value_global(hidden_states)

        # normalize
        global_query_vectors_only_global /= tf.math.sqrt(
            tf.cast(self.head_dim, dtype=global_query_vectors_only_global.dtype)
        )
        global_query_vectors_only_global = self.reshape_and_transpose(global_query_vectors_only_global, batch_size)
        global_key_vectors = self.reshape_and_transpose(global_key_vectors, batch_size)
        global_value_vectors = self.reshape_and_transpose(global_value_vectors, batch_size)

        # compute attn scores
        global_attn_scores = tf.matmul(global_query_vectors_only_global, global_key_vectors, transpose_b=True)

        if tf.executing_eagerly():
            tf.debugging.assert_equal(
                shape_list(global_attn_scores),
                [batch_size * self.num_heads, max_num_global_attn_indices, seq_len],
                message=f"global_attn_scores have the wrong size. Size should be {(batch_size * self.num_heads, max_num_global_attn_indices, seq_len)}, but is {shape_list(global_attn_scores)}.",
            )

        global_attn_scores = tf.reshape(
            global_attn_scores,
            (batch_size, self.num_heads, max_num_global_attn_indices, seq_len),
        )
        global_attn_scores_trans = tf.transpose(global_attn_scores, (0, 2, 1, 3))
        mask_shape = (shape_list(is_local_index_no_global_attn_nonzero)[0],) + tuple(
            shape_list(global_attn_scores_trans)[-2:]
        )
        global_attn_mask = tf.ones(mask_shape) * -10000.0
        global_attn_mask = tf.cast(global_attn_mask, dtype=global_attn_scores_trans.dtype)

        # scatter mask
        global_attn_scores_trans = tf.tensor_scatter_nd_update(
            global_attn_scores_trans,
            is_local_index_no_global_attn_nonzero,
            global_attn_mask,
        )
        global_attn_scores = tf.transpose(global_attn_scores_trans, (0, 2, 1, 3))

        # Lookahead mask
        # if is_look_ahead_mask:
        #     shape_attn = tf.shape(global_attn_scores)
        #
        #     look_ahead_mask = tf.cast(
        #         tf.reshape(tf.tile(tf.range(shape_attn[-1]), [tf.reduce_prod(shape_attn[:-1])]), shape_attn),
        #         is_index_global_attn_nonzero.dtype) > tf.tile(
        #         tf.expand_dims(
        #             tf.reshape(is_index_global_attn_nonzero[:, 1], (batch_size, 1, max_num_global_attn_indices)),
        #             -1),  [1, shape_attn[1], 1, 1])
        #
        #     global_attn_scores = tf.where(look_ahead_mask, -10000.0, global_attn_scores)

        def lookahead_func2(global_attn_scores, is_index_global_attn_nonzero, batch_size, max_num_global_attn_indices):
            shape_attn = tf.shape(global_attn_scores)

            look_ahead_mask = tf.cast(
                tf.reshape(tf.tile(tf.range(shape_attn[-1]), [tf.reduce_prod(shape_attn[:-1])]), shape_attn),
                is_index_global_attn_nonzero.dtype) > tf.tile(
                tf.expand_dims(
                    tf.reshape(is_index_global_attn_nonzero[:, 1], (batch_size, 1, max_num_global_attn_indices)),
                    -1), [1, shape_attn[1], 1, 1])

            global_attn_scores = tf.where(look_ahead_mask, -10000.0, global_attn_scores)

            return global_attn_scores

        global_attn_scores = tf.cond(is_look_ahead_mask,
                                     lambda: lookahead_func2(global_attn_scores,
                                                             is_index_global_attn_nonzero,
                                                             batch_size,
                                                             max_num_global_attn_indices),
                                     lambda: global_attn_scores)

        # mask global attn scores
        attn_mask = tf.tile(is_index_masked[:, None, None, :], (1, shape_list(global_attn_scores)[1], 1, 1))
        global_attn_scores = tf.where(attn_mask, -10000.0, global_attn_scores)
        global_attn_scores = tf.reshape(
            global_attn_scores,
            (batch_size * self.num_heads, max_num_global_attn_indices, seq_len),
        )

        # compute global attn probs
        global_attn_probs_float = tf.nn.softmax(global_attn_scores, axis=-1)

        # apply layer head masking
        if layer_head_mask is not None:
            if tf.executing_eagerly():
                tf.debugging.assert_equal(
                    shape_list(layer_head_mask),
                    [self.num_heads],
                    message=f"Head mask for a single layer should be of size {(self.num_heads)}, but is {shape_list(layer_head_mask)}",
                )
            global_attn_probs_float = tf.reshape(layer_head_mask, (1, -1, 1, 1)) * tf.reshape(
                global_attn_probs_float, (batch_size, self.num_heads, max_num_global_attn_indices, seq_len)
            )
            global_attn_probs_float = tf.reshape(
                global_attn_probs_float, (batch_size * self.num_heads, max_num_global_attn_indices, seq_len)
            )

        # dropout
        global_attn_probs = self.global_dropout(global_attn_probs_float, training=training)

        # global attn output
        global_attn_output = tf.matmul(global_attn_probs, global_value_vectors)

        if tf.executing_eagerly():
            tf.debugging.assert_equal(
                shape_list(global_attn_output),
                [batch_size * self.num_heads, max_num_global_attn_indices, self.head_dim],
                message=f"global_attn_output tensor has the wrong size. Size should be {(batch_size * self.num_heads, max_num_global_attn_indices, self.head_dim)}, but is {shape_list(global_attn_output)}.",
            )

        global_attn_output = tf.reshape(
            global_attn_output,
            (batch_size, self.num_heads, max_num_global_attn_indices, self.head_dim),
        )

        # get only non zero global attn output
        nonzero_global_attn_output = tf.gather_nd(
            tf.transpose(global_attn_output, (0, 2, 1, 3)),
            is_local_index_global_attn_nonzero,
        )
        nonzero_global_attn_output = tf.reshape(
            nonzero_global_attn_output,
            (shape_list(is_local_index_global_attn_nonzero)[0], -1),
        )

        # overwrite values with global attention
        attn_output = tf.tensor_scatter_nd_update(
            attn_output, is_index_global_attn_nonzero, nonzero_global_attn_output
        )

        global_attn_probs = tf.reshape(
            global_attn_probs, (batch_size, self.num_heads, max_num_global_attn_indices, seq_len)
        )

        return attn_output, global_attn_probs

    def reshape_and_transpose(self, vector, batch_size):
        return tf.reshape(
            tf.transpose(
                tf.reshape(vector, (batch_size, -1, self.num_heads, self.head_dim)),
                (0, 2, 1, 3),
            ),
            (batch_size * self.num_heads, -1, self.head_dim),
        )


class TFLongformerAttention(tf.keras.layers.Layer):
    def __init__(self, config, layer_id=0, **kwargs):
        super().__init__(**kwargs)

        self.self_attention = TFLongformerSelfAttention(config, layer_id, name="self")
        self.dense_output = TFLongformerSelfOutput(config, name="output")

    def prune_heads(self, heads):
        raise NotImplementedError

    def call(self, inputs, training=False):
        (
            hidden_states,
            encoder_outputs,
            attention_mask,
            layer_head_mask,
            is_index_masked,
            is_index_global_attn,
            is_global_attn,
            is_look_ahead_mask,
            output_length
        ) = inputs

        self_outputs = self.self_attention(
            [hidden_states, encoder_outputs, attention_mask, layer_head_mask, is_index_masked, is_index_global_attn,
             is_global_attn, is_look_ahead_mask, output_length],
            training=training,
        )
        attention_output = self.dense_output(self_outputs[0], hidden_states, training=training)
        outputs = (attention_output,) + self_outputs[1:]

        return outputs


class TFLongformerLayer(tf.keras.layers.Layer):
    def __init__(self, config, layer_id=0, **kwargs):
        super().__init__(**kwargs)

        self.attention = TFLongformerAttention(config, layer_id, name="attention")
        self.intermediate = TFLongformerIntermediate(config, name="intermediate")
        self.longformer_output = TFLongformerOutput(config, name="output")

    def call(self, inputs, training=False):
        (
            hidden_states,
            attention_mask,
            layer_head_mask,
            is_index_masked,
            is_index_global_attn,
            is_global_attn,
        ) = inputs

        is_look_ahead_mask = False
        attention_outputs = self.attention(
            [hidden_states, None, attention_mask, layer_head_mask, is_index_masked, is_index_global_attn,
             is_global_attn, is_look_ahead_mask, None],       # None --> Encoder outputs
            training=training,
        )
        attention_output = attention_outputs[0]
        intermediate_output = self.intermediate(attention_output)
        layer_output = self.longformer_output(intermediate_output, attention_output, training=training)
        outputs = (layer_output,) + attention_outputs[1:]  # add attentions if we output them

        return outputs


class TFLongformerDecLayer(tf.keras.layers.Layer):
    def __init__(self, config, layer_id=0, **kwargs):
        super().__init__(**kwargs)

        self.attention = TFLongformerAttention(config, layer_id, name="attention")
        self.intermediate = TFLongformerIntermediate(config, name="intermediate")
        self.longformer_output = TFLongformerOutput(config, name="output")

    def call(self, inputs, training=False):
        (
            hidden_states,
            encoder_outputs,
            attention_mask1,
            attention_mask2,
            layer_head_mask1,
            layer_head_mask2,
            is_index_masked,
            is_index_masked_enc,
            is_index_global_attn1,
            is_index_global_attn2,
            is_global_attn,
            output_length
        ) = inputs

        # Masked Multi-head Attention:
        attention_outputs1 = self.attention(
            [hidden_states, None, attention_mask1, layer_head_mask1, is_index_masked, is_index_global_attn1,
             is_global_attn, True, None],     # True --> is_look_ahead_mask, None --> Encoder outputs
            training=training,
        )
        attention_output1 = attention_outputs1[0]

        # Multi-head Attention (with encoder outputs):
        attention_outputs2 = self.attention(
            [attention_output1, encoder_outputs, attention_mask1, layer_head_mask2, is_index_masked_enc,
             is_index_global_attn2, is_global_attn, False, output_length],     # True --> is_look_ahead_mask, None --> Encoder outputs
            training=training,
        )

        attention_output2 = attention_outputs2[0]
        attention_outputs = list()
        for i in range(1, len(attention_outputs2)):
            attention_outputs += [(attention_outputs2[i],) + (attention_outputs1[i],)]     # Add masked attentions
        attention_outputs = tuple(attention_outputs)

        intermediate_output2 = self.intermediate(attention_output2)
        layer_output2 = self.longformer_output(intermediate_output2, attention_output2, training=training)
        outputs = (layer_output2,) + attention_outputs      #attention_outputs2[1:]  # TODO add first layer stuff

        return outputs


class TFLongformerEncoder(tf.keras.layers.Layer):
    def __init__(self, config, **kwargs):
        super().__init__(**kwargs)

        self.output_hidden_states = config.output_hidden_states
        self.output_attentions = config.output_attentions
        self.layer = [TFLongformerLayer(config, i, name=f"layer_._{i}") for i in range(config.num_hidden_layers)]

    def call(
        self,
        hidden_states,
        attention_mask=None,
        head_mask=None,
        padding_len=0,
        is_index_masked=None,
        is_index_global_attn=None,
        is_global_attn=None,
        output_attentions=None,
        output_hidden_states=None,
        return_dict=None,
        training=False,
    ):
        all_hidden_states = () if output_hidden_states else None
        all_attentions = all_global_attentions = () if output_attentions else None

        for idx, layer_module in enumerate(self.layer):
            if output_hidden_states:
                hidden_states_to_add = hidden_states[:, :-padding_len] if padding_len > 0 else hidden_states
                all_hidden_states = all_hidden_states + (hidden_states_to_add,)

            layer_outputs = layer_module(
                [
                    hidden_states,
                    attention_mask,
                    head_mask[idx] if head_mask is not None else None,
                    is_index_masked,
                    is_index_global_attn,
                    is_global_attn,
                ],
                training=training,
            )
            hidden_states = layer_outputs[0]

            if output_attentions:
                # bzs x seq_len x num_attn_heads x (num_global_attn + attention_window_len + 1) => bzs x num_attn_heads x seq_len x (num_global_attn + attention_window_len + 1)
                all_attentions = all_attentions + (tf.transpose(layer_outputs[1], (0, 2, 1, 3)),)

                # bzs x num_attn_heads x num_global_attn x seq_len => bzs x num_attn_heads x seq_len x num_global_attn
                all_global_attentions = all_global_attentions + (tf.transpose(layer_outputs[2], (0, 1, 3, 2)),)

        # Add last layer
        if output_hidden_states:
            hidden_states_to_add = hidden_states[:, :-padding_len] if padding_len > 0 else hidden_states
            all_hidden_states = all_hidden_states + (hidden_states_to_add,)

        if not return_dict:
            return tuple(
                v for v in [hidden_states, all_hidden_states, all_attentions, all_global_attentions] if v is not None
            )

        return TFLongformerBaseModelOutput(
            last_hidden_state=hidden_states,
            hidden_states=all_hidden_states,
            attentions=all_attentions,
            global_attentions=all_global_attentions,
        )


class TFLongformerDecoder(tf.keras.layers.Layer):
    def __init__(self, config, **kwargs):
        super().__init__(**kwargs)

        self.output_hidden_states = config.output_hidden_states
        self.output_attentions = config.output_attentions
        self.layer = [TFLongformerDecLayer(config, i, name=f"layer_._{i}") for i in range(config.num_hidden_layers)]   # TODO

    def call(
        self,
        hidden_states,
        encoder_outputs,        # Final hidden states output from encoder block
        attention_mask1=None,
        attention_mask2=None,
        head_mask1=None,
        head_mask2=None,
        padding_len=0,
        is_index_masked=None,
        is_index_masked_enc=None,
        is_index_global_attn1=None,
        is_index_global_attn2=None,
        is_global_attn=None,
        output_attentions=None,
        output_hidden_states=None,
        return_dict=None,
        training=False,
        output_length=None,
    ):
        all_hidden_states = () if output_hidden_states else None
        all_attentions = all_global_attentions = all_masked_attentions = () if output_attentions else None

        for idx, layer_module in enumerate(self.layer):
            if output_hidden_states:
                hidden_states_to_add = hidden_states[:, :-padding_len] if padding_len > 0 else hidden_states
                all_hidden_states = all_hidden_states + (hidden_states_to_add,)

            layer_outputs = layer_module(
                [
                    hidden_states,
                    encoder_outputs,
                    attention_mask1,
                    attention_mask2,
                    head_mask1[idx] if head_mask1 is not None else None,
                    head_mask2[idx] if head_mask2 is not None else None,
                    is_index_masked,
                    is_index_masked_enc,
                    is_index_global_attn1,
                    is_index_global_attn2,
                    is_global_attn,
                    output_length,
                ],
                training=training,
            )
            hidden_states = layer_outputs[0]

            if output_attentions:
                # bzs x seq_len x num_attn_heads x (num_global_attn + attention_window_len + 1) => bzs x num_attn_heads x seq_len x (num_global_attn + attention_window_len + 1)
                if isinstance(layer_outputs[1], tuple):
                    for i in range(len(layer_outputs[1])):
                        all_attentions = all_attentions + (tf.transpose(layer_outputs[1][i], (0, 2, 1, 3)),)
                else:
                    all_attentions = all_attentions + (tf.transpose(layer_outputs[1], (0, 2, 1, 3)),)

                # bzs x num_attn_heads x num_global_attn x seq_len => bzs x num_attn_heads x seq_len x num_global_attn
                if isinstance(layer_outputs[2], tuple):
                    for i in range(len(layer_outputs[2])):
                        all_global_attentions = all_global_attentions + (tf.transpose(layer_outputs[2][i], (0, 1, 3, 2)),)
                else:
                    all_global_attentions = all_global_attentions + (tf.transpose(layer_outputs[2], (0, 1, 3, 2)),)

        # Add last layer
        if output_hidden_states:
            hidden_states_to_add = hidden_states[:, :-padding_len] if padding_len > 0 else hidden_states
            all_hidden_states = all_hidden_states + (hidden_states_to_add,)

        if not return_dict:
            return tuple(
                v for v in [hidden_states, all_hidden_states, all_attentions, all_global_attentions] if v is not None
            )

        return TFLongformerBaseModelOutput(
            last_hidden_state=hidden_states,
            hidden_states=all_hidden_states,
            attentions=all_attentions,
            global_attentions=all_global_attentions,
        )



@keras_serializable
class TFLongformerMainLayer(tf.keras.layers.Layer):
    config_class = LongformerConfig

    def __init__(self, config, add_pooling_layer=True, **kwargs):
        super().__init__(**kwargs)

        if isinstance(config.attention_window, int):
            assert config.attention_window % 2 == 0, "`config.attention_window` has to be an even value"
            assert config.attention_window > 0, "`config.attention_window` has to be positive"
            config.attention_window = [config.attention_window] * config.num_hidden_layers  # one value per layer
        else:
            assert len(config.attention_window) == config.num_hidden_layers, (
                "`len(config.attention_window)` should equal `config.num_hidden_layers`. "
                f"Expected {config.num_hidden_layers}, given {len(config.attention_window)}"
            )

        self.config = config
        self.num_hidden_layers = config.num_hidden_layers
        self.initializer_range = config.initializer_range
        self.output_attentions = config.output_attentions
        self.output_hidden_states = config.output_hidden_states
        self.return_dict = config.use_return_dict
        self.pad_token_id = config.pad_token_id
        self.attention_window = config.attention_window
        self.embeddings = TFLongformerEmbeddings(config, name="embeddings")
        self.encoder = TFLongformerEncoder(config, name="encoder")
        self.pooler = TFLongformerPooler(config, name="pooler") if add_pooling_layer else None

    def get_input_embeddings(self):
        return self.embeddings

    def set_input_embeddings(self, value):
        self.embeddings.weight = value
        self.embeddings.vocab_size = shape_list(value)[0]

    def _prune_heads(self, heads_to_prune):
        """
        Prunes heads of the model. heads_to_prune: dict of {layer_num: list of heads to prune in this layer} See base
        class PreTrainedModel
        """
        raise NotImplementedError

    def call(
        self,
        input_ids=None,
        attention_mask=None,
        head_mask=None,
        global_attention_mask=None,
        token_type_ids=None,
        position_ids=None,
        inputs_embeds=None,
        output_attentions=None,
        output_hidden_states=None,
        return_dict=None,
        training=False,
        **kwargs,
    ):
        inputs = input_processing(
            func=self.call,
            config=self.config,
            input_ids=input_ids,
            attention_mask=attention_mask,
            head_mask=head_mask,
            global_attention_mask=global_attention_mask,
            token_type_ids=token_type_ids,
            position_ids=position_ids,
            inputs_embeds=inputs_embeds,
            output_attentions=output_attentions,
            output_hidden_states=output_hidden_states,
            return_dict=return_dict,
            training=training,
            kwargs_call=kwargs,
        )

        if inputs["input_ids"] is not None and inputs["inputs_embeds"] is not None:
            raise ValueError("You cannot specify both input_ids and inputs_embeds at the same time")
        elif inputs["input_ids"] is not None:
            input_shape = shape_list(inputs["input_ids"])
        elif inputs["inputs_embeds"] is not None:
            input_shape = shape_list(inputs["inputs_embeds"])[:-1]
        else:
            raise ValueError("You have to specify either input_ids or inputs_embeds")

        if inputs["attention_mask"] is None:
            inputs["attention_mask"] = tf.fill(input_shape, 1)

        if inputs["token_type_ids"] is None:
            inputs["token_type_ids"] = tf.fill(input_shape, 0)

        # merge `global_attention_mask` and `attention_mask`
        if inputs["global_attention_mask"] is not None:
            inputs["attention_mask"] = self._merge_to_attention_mask(
                inputs["attention_mask"], inputs["global_attention_mask"]
            )

        (
            padding_len,
            inputs["input_ids"],
            inputs["attention_mask"],
            inputs["token_type_ids"],
            inputs["position_ids"],
            inputs["inputs_embeds"],
        ) = self._pad_to_window_size(
            input_ids=inputs["input_ids"],
            attention_mask=inputs["attention_mask"],
            token_type_ids=inputs["token_type_ids"],
            position_ids=inputs["position_ids"],
            inputs_embeds=inputs["inputs_embeds"],
            pad_token_id=self.pad_token_id,
        )

        # is index masked or global attention
        is_index_masked = tf.math.less(inputs["attention_mask"], 1)
        is_index_global_attn = tf.math.greater(inputs["attention_mask"], 1)
        is_global_attn = tf.math.reduce_any(is_index_global_attn)

        # We create a 3D attention mask from a 2D tensor mask.
        # Sizes are [batch_size, to_seq_length, 1, 1]
        # So we can broadcast to [batch_size, num_heads, from_seq_length, to_seq_length]
        # this attention mask is more simple than the triangular masking of causal attention
        # used in OpenAI GPT, we just need to prepare the broadcast dimension here.
        attention_mask_shape = shape_list(inputs["attention_mask"])
        extended_attention_mask = tf.reshape(
            inputs["attention_mask"], (attention_mask_shape[0], attention_mask_shape[1], 1, 1)
        )

        # Since attention_mask is 1.0 for positions we want to attend locally and 0.0 for
        # masked and global attn positions, this operation will create a tensor which is 0.0 for
        # positions we want to attend and -10000.0 for masked positions.
        # Since we are adding it to the raw scores before the softmax, this is
        # effectively the same as removing these entirely.
        extended_attention_mask = tf.cast(tf.math.abs(1 - extended_attention_mask), tf.dtypes.float32) * -10000.0
        embedding_output = self.embeddings(
            inputs["input_ids"],
            inputs["position_ids"],
            inputs["token_type_ids"],
            inputs["inputs_embeds"],
            training=inputs["training"],
        )
        encoder_outputs = self.encoder(
            embedding_output,
            attention_mask=extended_attention_mask,
            head_mask=head_mask,
            padding_len=padding_len,
            is_index_masked=is_index_masked,
            is_index_global_attn=is_index_global_attn,
            is_global_attn=is_global_attn,
            output_attentions=inputs["output_attentions"],
            output_hidden_states=inputs["output_hidden_states"],
            return_dict=inputs["return_dict"],
            training=inputs["training"],
        )
        sequence_output = encoder_outputs[0]
        pooled_output = self.pooler(sequence_output) if self.pooler is not None else None

        # undo padding
        if padding_len > 0:
            # unpad `sequence_output` because the calling function is expecting a length == input_ids.size(1)
            sequence_output = sequence_output[:, :-padding_len]

        if not inputs["return_dict"]:
            return (
                sequence_output,
                pooled_output,
            ) + encoder_outputs[1:]

        return TFLongformerBaseModelOutputWithPooling(
            last_hidden_state=sequence_output,
            pooler_output=pooled_output,
            hidden_states=encoder_outputs.hidden_states,
            attentions=encoder_outputs.attentions,
            global_attentions=encoder_outputs.global_attentions,
        )

    def _pad_to_window_size(
        self,
        input_ids,
        attention_mask,
        token_type_ids,
        position_ids,
        inputs_embeds,
        pad_token_id,
    ):
        """A helper function to pad tokens and mask to work with implementation of Longformer selfattention."""
        # padding
        attention_window = (
            self.attention_window if isinstance(self.attention_window, int) else max(self.attention_window)
        )

        assert attention_window % 2 == 0, f"`attention_window` should be an even value. Given {attention_window}"

        input_shape = shape_list(input_ids) if input_ids is not None else shape_list(inputs_embeds)
        batch_size, seq_len = input_shape[:2]
        padding_len = (attention_window - seq_len % attention_window) % attention_window

        if padding_len > 0:
            logger.info(
                f"Input ids are automatically padded from {seq_len} to {seq_len + padding_len} to be a multiple of "
                f"`config.attention_window`: {attention_window}"
            )

        paddings = tf.convert_to_tensor([[0, 0], [0, padding_len]])

        if input_ids is not None:
            input_ids = tf.pad(input_ids, paddings, constant_values=pad_token_id)

        if position_ids is not None:
            # pad with position_id = pad_token_id as in modeling_roberta.RobertaEmbeddings
            position_ids = tf.pad(position_ids, paddings, constant_values=pad_token_id)

        if inputs_embeds is not None:

            def pad_embeddings():
                input_ids_padding = tf.fill((batch_size, padding_len), self.pad_token_id)
                inputs_embeds_padding = self.embeddings(input_ids_padding)
                return tf.concat([inputs_embeds, inputs_embeds_padding], axis=-2)

            inputs_embeds = tf.cond(tf.math.greater(padding_len, 0), pad_embeddings, lambda: inputs_embeds)

        attention_mask = tf.pad(attention_mask, paddings, constant_values=False)  # no attention on the padding tokens
        token_type_ids = tf.pad(token_type_ids, paddings, constant_values=0)  # pad with token_type_id = 0

        return (
            padding_len,
            input_ids,
            attention_mask,
            token_type_ids,
            position_ids,
            inputs_embeds,
        )

    @staticmethod
    def _merge_to_attention_mask(attention_mask: tf.Tensor, global_attention_mask: tf.Tensor):
        # longformer self attention expects attention mask to have 0 (no attn), 1 (local attn), 2 (global attn)
        # (global_attention_mask + 1) => 1 for local attention, 2 for global attention
        # => final attention_mask => 0 for no attention, 1 for local attention 2 for global attention
        if attention_mask is not None:
            attention_mask = attention_mask * (global_attention_mask + 1)
        else:
            # simply use `global_attention_mask` as `attention_mask`
            # if no `attention_mask` is given
            attention_mask = global_attention_mask + 1

        return attention_mask


class TFLongformerPreTrainedModel(TFPreTrainedModel):
    """
    An abstract class to handle weights initialization and a simple interface for downloading and loading pretrained
    models.
    """

    config_class = LongformerConfig
    base_model_prefix = "longformer"

    @property
    def dummy_inputs(self):
        input_ids = tf.convert_to_tensor([[7, 6, 0, 0, 1], [1, 2, 3, 0, 0], [0, 0, 0, 4, 5]])
        # make sure global layers are initialized
        attention_mask = tf.convert_to_tensor([[1, 1, 0, 0, 1], [1, 1, 1, 0, 0], [1, 0, 0, 1, 1]])
        global_attention_mask = tf.convert_to_tensor([[0, 0, 0, 0, 1], [0, 0, 1, 0, 0], [0, 0, 0, 0, 1]])
        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "global_attention_mask": global_attention_mask,
        }

    @tf.function(
        input_signature=[
            {
                "input_ids": tf.TensorSpec((None, None), tf.int32, name="input_ids"),
                "attention_mask": tf.TensorSpec((None, None), tf.int32, name="attention_mask"),
            }
        ]
    )
    def serving(self, inputs):
        output = self.call(inputs)

        return self.serving_output(output)


LONGFORMER_START_DOCSTRING = r"""

    This model inherits from :class:`~transformers.TFPreTrainedModel`. Check the superclass documentation for the
    generic methods the library implements for all its model (such as downloading or saving, resizing the input
    embeddings, pruning heads etc.)

    This model is also a `tf.keras.Model <https://www.tensorflow.org/api_docs/python/tf/keras/Model>`__ subclass. Use
    it as a regular TF 2.0 Keras Model and refer to the TF 2.0 documentation for all matter related to general usage
    and behavior.

    .. note::

        TF 2.0 models accepts two formats as inputs:

        - having all inputs as keyword arguments (like PyTorch models), or
        - having all inputs as a list, tuple or dict in the first positional arguments.

        This second option is useful when using :meth:`tf.keras.Model.fit` method which currently requires having all
        the tensors in the first argument of the model call function: :obj:`model(inputs)`.

        If you choose this second option, there are three possibilities you can use to gather all the input Tensors in
        the first positional argument :

        - a single Tensor with :obj:`input_ids` only and nothing else: :obj:`model(inputs_ids)`
        - a list of varying length with one or several input Tensors IN THE ORDER given in the docstring:
          :obj:`model([input_ids, attention_mask])` or :obj:`model([input_ids, attention_mask, token_type_ids])`
        - a dictionary with one or several input Tensors associated to the input names given in the docstring:
          :obj:`model({"input_ids": input_ids, "token_type_ids": token_type_ids})`

    Parameters:
        config (:class:`~transformers.LongformerConfig`): Model configuration class with all the parameters of the model.
            Initializing with a config file does not load the weights associated with the model, only the
            configuration. Check out the :meth:`~transformers.PreTrainedModel.from_pretrained` method to load the model
            weights.
"""


LONGFORMER_INPUTS_DOCSTRING = r"""
    Args:
        input_ids (:obj:`tf.Tensor` of shape :obj:`({0})`):
            Indices of input sequence tokens in the vocabulary.

            Indices can be obtained using :class:`~transformers.LongformerTokenizer`. See
            :func:`transformers.PreTrainedTokenizer.__call__` and :func:`transformers.PreTrainedTokenizer.encode` for
            details.

            `What are input IDs? <../glossary.html#input-ids>`__
        attention_mask (:obj:`tf.Tensor` of shape :obj:`({0})`, `optional`):
            Mask to avoid performing attention on padding token indices. Mask values selected in ``[0, 1]``:

            - 1 for tokens that are **not masked**,
            - 0 for tokens that are **masked**.

            `What are attention masks? <../glossary.html#attention-mask>`__
        head_mask (:obj:`tf.Tensor` of shape :obj:`(encoder_layers, encoder_attention_heads)`, `optional`):
            Mask to nullify selected heads of the attention modules. Mask values selected in ``[0, 1]``:

            - 1 indicates the head is **not masked**,
            - 0 indicates the head is **masked**.

        global_attention_mask (:obj:`tf.Tensor` of shape :obj:`({0})`, `optional`):
            Mask to decide the attention given on each token, local attention or global attention. Tokens with global
            attention attends to all other tokens, and all other tokens attend to them. This is important for
            task-specific finetuning because it makes the model more flexible at representing the task. For example,
            for classification, the <s> token should be given global attention. For QA, all question tokens should also
            have global attention. Please refer to the `Longformer paper <https://arxiv.org/abs/2004.05150>`__ for more
            details. Mask values selected in ``[0, 1]``:

            - 0 for local attention (a sliding window attention),
            - 1 for global attention (tokens that attend to all other tokens, and all other tokens attend to them).

        token_type_ids (:obj:`tf.Tensor` of shape :obj:`({0})`, `optional`):
            Segment token indices to indicate first and second portions of the inputs. Indices are selected in ``[0,
            1]``:

            - 0 corresponds to a `sentence A` token,
            - 1 corresponds to a `sentence B` token.

            `What are token type IDs? <../glossary.html#token-type-ids>`__
        position_ids (:obj:`tf.Tensor` of shape :obj:`({0})`, `optional`):
            Indices of positions of each input sequence tokens in the position embeddings. Selected in the range ``[0,
            config.max_position_embeddings - 1]``.

            `What are position IDs? <../glossary.html#position-ids>`__
        inputs_embeds (:obj:`tf.Tensor` of shape :obj:`({0}, hidden_size)`, `optional`):
            Optionally, instead of passing :obj:`input_ids` you can choose to directly pass an embedded representation.
            This is useful if you want more control over how to convert :obj:`input_ids` indices into associated
            vectors than the model's internal embedding lookup matrix.
        output_attentions (:obj:`bool`, `optional`):
            Whether or not to return the attentions tensors of all attention layers. See ``attentions`` under returned
            tensors for more detail. This argument can be used only in eager mode, in graph mode the value in the
            config will be used instead.
        output_hidden_states (:obj:`bool`, `optional`):
            Whether or not to return the hidden states of all layers. See ``hidden_states`` under returned tensors for
            more detail. This argument can be used only in eager mode, in graph mode the value in the config will be
            used instead.
        return_dict (:obj:`bool`, `optional`):
            Whether or not to return a :class:`~transformers.file_utils.ModelOutput` instead of a plain tuple. This
            argument can be used in eager mode, in graph mode the value will always be set to True.
        training (:obj:`bool`, `optional`, defaults to :obj:`False`):
            Whether or not to use the model in training mode (some modules like dropout modules have different
            behaviors between training and evaluation).
"""


@add_start_docstrings(
    "The bare Longformer Model outputting raw hidden-states without any specific head on top.",
    LONGFORMER_START_DOCSTRING,
)
class TFLongformerModel(TFLongformerPreTrainedModel):
    """

    This class copies code from :class:`~transformers.TFRobertaModel` and overwrites standard self-attention with
    longformer self-attention to provide the ability to process long sequences following the self-attention approach
    described in `Longformer: the Long-Document Transformer <https://arxiv.org/abs/2004.05150>`__ by Iz Beltagy,
    Matthew E. Peters, and Arman Cohan. Longformer self-attention combines a local (sliding window) and global
    attention to extend to long documents without the O(n^2) increase in memory and compute.

    The self-attention module :obj:`TFLongformerSelfAttention` implemented here supports the combination of local and
    global attention but it lacks support for autoregressive attention and dilated attention. Autoregressive and
    dilated attention are more relevant for autoregressive language modeling than finetuning on downstream tasks.
    Future release will add support for autoregressive attention, but the support for dilated attention requires a
    custom CUDA kernel to be memory and compute efficient.

    """

    def __init__(self, config, *inputs, **kwargs):
        super().__init__(config, *inputs, **kwargs)

        self.longformer = TFLongformerMainLayer(config, name="longformer")

    @add_start_docstrings_to_model_forward(LONGFORMER_INPUTS_DOCSTRING.format("batch_size, sequence_length"))
    def call(
        self,
        input_ids=None,
        attention_mask=None,
        head_mask=None,
        global_attention_mask=None,
        token_type_ids=None,
        position_ids=None,
        inputs_embeds=None,
        output_attentions=None,
        output_hidden_states=None,
        return_dict=None,
        training=False,
        **kwargs,
    ):
        inputs = input_processing(
            func=self.call,
            config=self.config,
            input_ids=input_ids,
            attention_mask=attention_mask,
            head_mask=head_mask,
            global_attention_mask=global_attention_mask,
            token_type_ids=token_type_ids,
            position_ids=position_ids,
            inputs_embeds=inputs_embeds,
            output_attentions=output_attentions,
            output_hidden_states=output_hidden_states,
            return_dict=return_dict,
            training=training,
            kwargs_call=kwargs,
        )
        outputs = self.longformer(
            input_ids=inputs["input_ids"],
            attention_mask=inputs["attention_mask"],
            head_mask=inputs["head_mask"],
            global_attention_mask=inputs["global_attention_mask"],
            token_type_ids=inputs["token_type_ids"],
            position_ids=inputs["position_ids"],
            inputs_embeds=inputs["inputs_embeds"],
            output_attentions=inputs["output_attentions"],
            output_hidden_states=inputs["output_hidden_states"],
            return_dict=inputs["return_dict"],
            training=inputs["training"],
        )

        return outputs

    def serving_output(self, output):
        hs = tf.convert_to_tensor(output.hidden_states) if self.config.output_hidden_states else None
        attns = tf.convert_to_tensor(output.attentions) if self.config.output_attentions else None
        g_attns = tf.convert_to_tensor(output.global_attentions) if self.config.output_attentions else None

        return TFLongformerBaseModelOutputWithPooling(
            last_hidden_state=output.last_hidden_state,
            pooler_output=output.pooler_output,
            hidden_states=hs,
            attentions=attns,
            global_attentions=g_attns,
        )


@add_start_docstrings(
    """Longformer Model with a `language modeling` head on top. """,
    LONGFORMER_START_DOCSTRING,
)
class TFLongformerForMaskedLM(TFLongformerPreTrainedModel, TFMaskedLanguageModelingLoss):
    # names with a '.' represents the authorized unexpected/missing layers when a TF model is loaded from a PT model
    _keys_to_ignore_on_load_unexpected = [r"pooler"]

    def __init__(self, config, *inputs, **kwargs):
        super().__init__(config, *inputs, **kwargs)

        self.longformer = TFLongformerMainLayer(config, add_pooling_layer=False, name="longformer")
        self.lm_head = TFLongformerLMHead(config, self.longformer.embeddings, name="lm_head")

    def get_lm_head(self):
        return self.lm_head

    def get_prefix_bias_name(self):
        warnings.warn("The method get_prefix_bias_name is deprecated. Please use `get_bias` instead.", FutureWarning)
        return self.name + "/" + self.lm_head.name


class TFLongformerClassificationHead(tf.keras.layers.Layer):
    """Head for sentence-level classification tasks."""

    def __init__(self, config, **kwargs):
        super().__init__(**kwargs)
        self.dense = tf.keras.layers.Dense(
            config.hidden_size,
            kernel_initializer=get_initializer(config.initializer_range),
            activation="tanh",
            name="dense",
        )
        self.dropout = tf.keras.layers.Dropout(config.hidden_dropout_prob)
        self.out_proj = tf.keras.layers.Dense(
            config.num_labels, kernel_initializer=get_initializer(config.initializer_range), name="out_proj"
        )

    def call(self, hidden_states, training=False):
        hidden_states = hidden_states[:, 0, :]  # take <s> token (equiv. to [CLS])
        hidden_states = self.dropout(hidden_states, training=training)
        hidden_states = self.dense(hidden_states)
        hidden_states = self.dropout(hidden_states, training=training)
        output = self.out_proj(hidden_states)
        return output
