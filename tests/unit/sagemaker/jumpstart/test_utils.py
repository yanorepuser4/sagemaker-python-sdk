# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at
#
#     http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.
from __future__ import absolute_import
import os
from unittest import TestCase
from mock.mock import Mock, patch
import pytest
import boto3
import random
from sagemaker import session
from sagemaker.jumpstart import utils
from sagemaker.jumpstart.constants import (
    DEFAULT_JUMPSTART_SAGEMAKER_SESSION,
    ENV_VARIABLE_DISABLE_JUMPSTART_LOGGING,
    ENV_VARIABLE_JUMPSTART_CONTENT_BUCKET_OVERRIDE,
    ENV_VARIABLE_JUMPSTART_GATED_CONTENT_BUCKET_OVERRIDE,
    EXTRA_MODEL_ID_TAGS,
    EXTRA_MODEL_VERSION_TAGS,
    JUMPSTART_DEFAULT_REGION_NAME,
    JUMPSTART_GATED_AND_PUBLIC_BUCKET_NAME_SET,
    JUMPSTART_LOGGER,
    JUMPSTART_REGION_NAME_SET,
    JUMPSTART_RESOURCE_BASE_NAME,
    JumpStartScriptScope,
)
from functools import partial
from sagemaker.jumpstart.enums import JumpStartTag, MIMEType, JumpStartModelType
from sagemaker.jumpstart.exceptions import (
    DeprecatedJumpStartModelError,
    VulnerableJumpStartModelError,
)
from sagemaker.jumpstart.types import (
    JumpStartBenchmarkStat,
    JumpStartModelHeader,
    JumpStartVersionedModelId,
)
from tests.unit.sagemaker.jumpstart.utils import (
    get_base_spec_with_prototype_configs,
    get_spec_from_base_spec,
    get_special_model_spec,
    get_prototype_manifest,
    get_base_deployment_configs,
)
from mock import MagicMock


MOCK_CLIENT = MagicMock()


def random_jumpstart_s3_uri(key):
    return f"s3://{random.choice(list(JUMPSTART_GATED_AND_PUBLIC_BUCKET_NAME_SET))}/{key}"


def test_get_jumpstart_content_bucket():
    bad_region = "bad_region"
    assert bad_region not in JUMPSTART_REGION_NAME_SET
    with pytest.raises(ValueError):
        utils.get_jumpstart_content_bucket(bad_region)


def test_get_jumpstart_content_bucket_no_args():
    assert (
        utils.get_jumpstart_content_bucket(JUMPSTART_DEFAULT_REGION_NAME)
        == utils.get_jumpstart_content_bucket()
    )


def test_get_jumpstart_content_bucket_override():
    with patch.dict(os.environ, {ENV_VARIABLE_JUMPSTART_CONTENT_BUCKET_OVERRIDE: "some-val"}):
        with patch("logging.Logger.info") as mocked_info_log:
            random_region = "random_region"
            assert "some-val" == utils.get_jumpstart_content_bucket(random_region)
            mocked_info_log.assert_called_with("Using JumpStart bucket override: 'some-val'")


def test_get_jumpstart_gated_content_bucket():
    bad_region = "bad_region"
    assert bad_region not in JUMPSTART_REGION_NAME_SET
    with pytest.raises(ValueError):
        utils.get_jumpstart_gated_content_bucket(bad_region)


def test_get_jumpstart_gated_content_bucket_no_args():
    assert (
        utils.get_jumpstart_gated_content_bucket(JUMPSTART_DEFAULT_REGION_NAME)
        == utils.get_jumpstart_gated_content_bucket()
    )


def test_get_jumpstart_gated_content_bucket_override():
    with patch.dict(os.environ, {ENV_VARIABLE_JUMPSTART_GATED_CONTENT_BUCKET_OVERRIDE: "some-val"}):
        with patch("logging.Logger.info") as mocked_info_log:
            random_region = "random_region"
            assert "some-val" == utils.get_jumpstart_gated_content_bucket(random_region)
            mocked_info_log.assert_called_once_with(
                "Using JumpStart gated bucket override: 'some-val'"
            )


def test_get_jumpstart_launched_regions_message():

    with patch("sagemaker.jumpstart.constants.JUMPSTART_REGION_NAME_SET", {}):
        assert (
            utils.get_jumpstart_launched_regions_message()
            == "JumpStart is not available in any region."
        )

    with patch("sagemaker.jumpstart.constants.JUMPSTART_REGION_NAME_SET", {"some_region"}):
        assert (
            utils.get_jumpstart_launched_regions_message()
            == "JumpStart is available in some_region region."
        )

    with patch(
        "sagemaker.jumpstart.constants.JUMPSTART_REGION_NAME_SET", {"some_region1", "some_region2"}
    ):
        assert (
            utils.get_jumpstart_launched_regions_message()
            == "JumpStart is available in some_region1 and some_region2 regions."
        )

    with patch("sagemaker.jumpstart.constants.JUMPSTART_REGION_NAME_SET", {"a", "b", "c"}):
        assert (
            utils.get_jumpstart_launched_regions_message()
            == "JumpStart is available in a, b, and c regions."
        )


def test_get_formatted_manifest():
    mock_manifest = [
        {
            "model_id": "tensorflow-ic-imagenet-inception-v3-classification-4",
            "version": "1.0.0",
            "min_version": "2.49.0",
            "spec_key": "community_models_specs/tensorflow-ic-imagenet-inception-v3-classification-4/specs_v1.0.0.json",
        },
    ]

    assert utils.get_formatted_manifest(mock_manifest) == {
        JumpStartVersionedModelId(
            "tensorflow-ic-imagenet-inception-v3-classification-4", "1.0.0"
        ): JumpStartModelHeader(mock_manifest[0])
    }

    assert utils.get_formatted_manifest([]) == {}


def test_parse_sagemaker_version():

    with patch("sagemaker.__version__", "1.2.3"):
        assert utils.parse_sagemaker_version() == "1.2.3"

    with patch("sagemaker.__version__", "1.2.3.3332j"):
        assert utils.parse_sagemaker_version() == "1.2.3"

    with patch("sagemaker.__version__", "1.2.3."):
        assert utils.parse_sagemaker_version() == "1.2.3"

    with pytest.raises(ValueError):
        with patch("sagemaker.__version__", "1.2.3dfsdfs"):
            utils.parse_sagemaker_version()

    with pytest.raises(RuntimeError):
        with patch("sagemaker.__version__", "1.2"):
            utils.parse_sagemaker_version()

    with pytest.raises(RuntimeError):
        with patch("sagemaker.__version__", "1"):
            utils.parse_sagemaker_version()

    with pytest.raises(RuntimeError):
        with patch("sagemaker.__version__", ""):
            utils.parse_sagemaker_version()

    with pytest.raises(RuntimeError):
        with patch("sagemaker.__version__", "1.2.3.4.5"):
            utils.parse_sagemaker_version()


@patch("sagemaker.jumpstart.utils.parse_sagemaker_version")
@patch("sagemaker.jumpstart.accessors.SageMakerSettings._parsed_sagemaker_version", "")
def test_get_sagemaker_version(patched_parse_sm_version: Mock):
    utils.get_sagemaker_version()
    utils.get_sagemaker_version()
    utils.get_sagemaker_version()
    assert patched_parse_sm_version.called_only_once()


def test_is_jumpstart_model_uri():

    assert not utils.is_jumpstart_model_uri("fdsfdsf")
    assert not utils.is_jumpstart_model_uri("s3://not-jumpstart-bucket/sdfsdfds")
    assert not utils.is_jumpstart_model_uri("some/actual/localfile")

    assert utils.is_jumpstart_model_uri(
        random_jumpstart_s3_uri("source_directory_tarballs/sourcedir.tar.gz")
    )
    assert utils.is_jumpstart_model_uri(random_jumpstart_s3_uri("random_key"))


def test_add_jumpstart_model_id_version_tags():
    tags = None
    model_id = "model_id"
    version = "version"
    assert [
        {"Key": "sagemaker-sdk:jumpstart-model-id", "Value": "model_id"},
        {"Key": "sagemaker-sdk:jumpstart-model-version", "Value": "version"},
    ] == utils.add_jumpstart_model_id_version_tags(
        tags=tags, model_id=model_id, model_version=version
    )

    tags = [
        {"Key": "sagemaker-sdk:jumpstart-model-id", "Value": "model_id_2"},
        {"Key": "sagemaker-sdk:jumpstart-model-version", "Value": "version_2"},
    ]
    model_id = "model_id"
    version = "version"
    # If tags are already present, don't modify existing tags
    assert [
        {"Key": "sagemaker-sdk:jumpstart-model-id", "Value": "model_id_2"},
        {"Key": "sagemaker-sdk:jumpstart-model-version", "Value": "version_2"},
    ] == utils.add_jumpstart_model_id_version_tags(
        tags=tags, model_id=model_id, model_version=version
    )

    tags = [
        {"Key": "random key", "Value": "random_value"},
    ]
    model_id = "model_id"
    version = "version"
    assert [
        {"Key": "random key", "Value": "random_value"},
        {"Key": "sagemaker-sdk:jumpstart-model-id", "Value": "model_id"},
        {"Key": "sagemaker-sdk:jumpstart-model-version", "Value": "version"},
    ] == utils.add_jumpstart_model_id_version_tags(
        tags=tags, model_id=model_id, model_version=version
    )

    tags = [
        {"Key": "sagemaker-sdk:jumpstart-model-id", "Value": "model_id_2"},
    ]
    model_id = "model_id"
    version = "version"
    # If tags are already present, don't modify existing tags
    assert [
        {"Key": "sagemaker-sdk:jumpstart-model-id", "Value": "model_id_2"},
        {"Key": "sagemaker-sdk:jumpstart-model-version", "Value": "version"},
    ] == utils.add_jumpstart_model_id_version_tags(
        tags=tags, model_id=model_id, model_version=version
    )

    tags = [
        {"Key": "random key", "Value": "random_value"},
    ]
    model_id = None
    version = None
    assert [
        {"Key": "random key", "Value": "random_value"},
    ] == utils.add_jumpstart_model_id_version_tags(
        tags=tags, model_id=model_id, model_version=version
    )


def test_add_jumpstart_uri_tags_inference():
    tags = None
    inference_model_uri = "dfsdfsd"
    inference_script_uri = "dfsdfs"
    assert (
        utils.add_jumpstart_uri_tags(
            tags=tags,
            inference_model_uri=inference_model_uri,
            inference_script_uri=inference_script_uri,
        )
        is None
    )

    tags = []
    inference_model_uri = "dfsdfsd"
    inference_script_uri = "dfsdfs"
    assert (
        utils.add_jumpstart_uri_tags(
            tags=tags,
            inference_model_uri=inference_model_uri,
            inference_script_uri=inference_script_uri,
        )
        == []
    )

    tags = [{"Key": "some", "Value": "tag"}]
    inference_model_uri = "dfsdfsd"
    inference_script_uri = "dfsdfs"
    assert utils.add_jumpstart_uri_tags(
        tags=tags,
        inference_model_uri=inference_model_uri,
        inference_script_uri=inference_script_uri,
    ) == [{"Key": "some", "Value": "tag"}]

    tags = None
    inference_model_uri = random_jumpstart_s3_uri("random_key")
    inference_script_uri = "dfsdfs"
    assert utils.add_jumpstart_uri_tags(
        tags=tags,
        inference_model_uri=inference_model_uri,
        inference_script_uri=inference_script_uri,
    ) == [{"Key": JumpStartTag.INFERENCE_MODEL_URI.value, "Value": inference_model_uri}]

    tags = []
    inference_model_uri = random_jumpstart_s3_uri("random_key")
    inference_script_uri = "dfsdfs"
    assert utils.add_jumpstart_uri_tags(
        tags=tags,
        inference_model_uri=inference_model_uri,
        inference_script_uri=inference_script_uri,
    ) == [{"Key": JumpStartTag.INFERENCE_MODEL_URI.value, "Value": inference_model_uri}]

    tags = []
    inference_model_uri = {"S3DataSource": {"S3Uri": random_jumpstart_s3_uri("random_key")}}
    inference_script_uri = "dfsdfs"
    assert utils.add_jumpstart_uri_tags(
        tags=tags,
        inference_model_uri=inference_model_uri,
        inference_script_uri=inference_script_uri,
    ) == [
        {
            "Key": JumpStartTag.INFERENCE_MODEL_URI.value,
            "Value": inference_model_uri["S3DataSource"]["S3Uri"],
        }
    ]

    tags = []
    inference_model_uri = {"S3DataSource": {"S3Uri": random_jumpstart_s3_uri("random_key/prefix/")}}
    inference_script_uri = "dfsdfs"
    assert utils.add_jumpstart_uri_tags(
        tags=tags,
        inference_model_uri=inference_model_uri,
        inference_script_uri=inference_script_uri,
    ) == [
        {
            "Key": JumpStartTag.INFERENCE_MODEL_URI.value,
            "Value": inference_model_uri["S3DataSource"]["S3Uri"],
        }
    ]

    tags = [{"Key": "some", "Value": "tag"}]
    inference_model_uri = random_jumpstart_s3_uri("random_key")
    inference_script_uri = "dfsdfs"
    assert utils.add_jumpstart_uri_tags(
        tags=tags,
        inference_model_uri=inference_model_uri,
        inference_script_uri=inference_script_uri,
    ) == [
        {"Key": "some", "Value": "tag"},
        {"Key": JumpStartTag.INFERENCE_MODEL_URI.value, "Value": inference_model_uri},
    ]

    tags = None
    inference_script_uri = random_jumpstart_s3_uri("random_key")
    inference_model_uri = "dfsdfs"
    assert utils.add_jumpstart_uri_tags(
        tags=tags,
        inference_model_uri=inference_model_uri,
        inference_script_uri=inference_script_uri,
    ) == [{"Key": JumpStartTag.INFERENCE_SCRIPT_URI.value, "Value": inference_script_uri}]

    tags = []
    inference_script_uri = random_jumpstart_s3_uri("random_key")
    inference_model_uri = "dfsdfs"
    assert utils.add_jumpstart_uri_tags(
        tags=tags,
        inference_model_uri=inference_model_uri,
        inference_script_uri=inference_script_uri,
    ) == [{"Key": JumpStartTag.INFERENCE_SCRIPT_URI.value, "Value": inference_script_uri}]

    tags = [{"Key": "some", "Value": "tag"}]
    inference_script_uri = random_jumpstart_s3_uri("random_key")
    inference_model_uri = "dfsdfs"
    assert utils.add_jumpstart_uri_tags(
        tags=tags,
        inference_model_uri=inference_model_uri,
        inference_script_uri=inference_script_uri,
    ) == [
        {"Key": "some", "Value": "tag"},
        {"Key": JumpStartTag.INFERENCE_SCRIPT_URI.value, "Value": inference_script_uri},
    ]

    tags = None
    inference_script_uri = random_jumpstart_s3_uri("random_key")
    inference_model_uri = random_jumpstart_s3_uri("random_key")
    assert utils.add_jumpstart_uri_tags(
        tags=tags,
        inference_model_uri=inference_model_uri,
        inference_script_uri=inference_script_uri,
    ) == [
        {
            "Key": JumpStartTag.INFERENCE_MODEL_URI.value,
            "Value": inference_model_uri,
        },
        {"Key": JumpStartTag.INFERENCE_SCRIPT_URI.value, "Value": inference_script_uri},
    ]

    tags = []
    inference_script_uri = random_jumpstart_s3_uri("random_key")
    inference_model_uri = random_jumpstart_s3_uri("random_key")
    assert utils.add_jumpstart_uri_tags(
        tags=tags,
        inference_model_uri=inference_model_uri,
        inference_script_uri=inference_script_uri,
    ) == [
        {
            "Key": JumpStartTag.INFERENCE_MODEL_URI.value,
            "Value": inference_model_uri,
        },
        {"Key": JumpStartTag.INFERENCE_SCRIPT_URI.value, "Value": inference_script_uri},
    ]

    tags = [{"Key": "some", "Value": "tag"}]
    inference_script_uri = random_jumpstart_s3_uri("random_key")
    inference_model_uri = random_jumpstart_s3_uri("random_key")
    assert utils.add_jumpstart_uri_tags(
        tags=tags,
        inference_model_uri=inference_model_uri,
        inference_script_uri=inference_script_uri,
    ) == [
        {"Key": "some", "Value": "tag"},
        {
            "Key": JumpStartTag.INFERENCE_MODEL_URI.value,
            "Value": inference_model_uri,
        },
        {"Key": JumpStartTag.INFERENCE_SCRIPT_URI.value, "Value": inference_script_uri},
    ]

    tags = [{"Key": JumpStartTag.INFERENCE_MODEL_URI.value, "Value": "garbage-value"}]
    inference_script_uri = random_jumpstart_s3_uri("random_key")
    inference_model_uri = random_jumpstart_s3_uri("random_key")
    assert utils.add_jumpstart_uri_tags(
        tags=tags,
        inference_model_uri=inference_model_uri,
        inference_script_uri=inference_script_uri,
    ) == [
        {"Key": JumpStartTag.INFERENCE_MODEL_URI.value, "Value": "garbage-value"},
        {"Key": JumpStartTag.INFERENCE_SCRIPT_URI.value, "Value": inference_script_uri},
    ]

    tags = [{"Key": JumpStartTag.INFERENCE_SCRIPT_URI.value, "Value": "garbage-value"}]
    inference_script_uri = random_jumpstart_s3_uri("random_key")
    inference_model_uri = random_jumpstart_s3_uri("random_key")
    assert utils.add_jumpstart_uri_tags(
        tags=tags,
        inference_model_uri=inference_model_uri,
        inference_script_uri=inference_script_uri,
    ) == [
        {"Key": JumpStartTag.INFERENCE_SCRIPT_URI.value, "Value": "garbage-value"},
        {"Key": JumpStartTag.INFERENCE_MODEL_URI.value, "Value": inference_model_uri},
    ]

    tags = [
        {"Key": JumpStartTag.INFERENCE_SCRIPT_URI.value, "Value": "garbage-value"},
        {"Key": JumpStartTag.INFERENCE_MODEL_URI.value, "Value": "garbage-value-2"},
    ]
    inference_script_uri = random_jumpstart_s3_uri("random_key")
    inference_model_uri = random_jumpstart_s3_uri("random_key")
    assert utils.add_jumpstart_uri_tags(
        tags=tags,
        inference_model_uri=inference_model_uri,
        inference_script_uri=inference_script_uri,
    ) == [
        {"Key": JumpStartTag.INFERENCE_SCRIPT_URI.value, "Value": "garbage-value"},
        {"Key": JumpStartTag.INFERENCE_MODEL_URI.value, "Value": "garbage-value-2"},
    ]


def test_add_jumpstart_uri_tags_training():
    tags = None
    training_model_uri = "dfsdfsd"
    training_script_uri = "dfsdfs"
    assert (
        utils.add_jumpstart_uri_tags(
            tags=tags,
            training_model_uri=training_model_uri,
            training_script_uri=training_script_uri,
        )
        is None
    )

    tags = []
    training_model_uri = "dfsdfsd"
    training_script_uri = "dfsdfs"
    assert (
        utils.add_jumpstart_uri_tags(
            tags=tags,
            training_model_uri=training_model_uri,
            training_script_uri=training_script_uri,
        )
        == []
    )

    tags = [{"Key": "some", "Value": "tag"}]
    training_model_uri = "dfsdfsd"
    training_script_uri = "dfsdfs"
    assert utils.add_jumpstart_uri_tags(
        tags=tags,
        training_model_uri=training_model_uri,
        training_script_uri=training_script_uri,
    ) == [{"Key": "some", "Value": "tag"}]

    tags = None
    training_model_uri = random_jumpstart_s3_uri("random_key")
    training_script_uri = "dfsdfs"
    assert utils.add_jumpstart_uri_tags(
        tags=tags,
        training_model_uri=training_model_uri,
        training_script_uri=training_script_uri,
    ) == [{"Key": JumpStartTag.TRAINING_MODEL_URI.value, "Value": training_model_uri}]

    tags = []
    training_model_uri = random_jumpstart_s3_uri("random_key")
    training_script_uri = "dfsdfs"
    assert utils.add_jumpstart_uri_tags(
        tags=tags,
        training_model_uri=training_model_uri,
        training_script_uri=training_script_uri,
    ) == [{"Key": JumpStartTag.TRAINING_MODEL_URI.value, "Value": training_model_uri}]

    tags = [{"Key": "some", "Value": "tag"}]
    training_model_uri = random_jumpstart_s3_uri("random_key")
    training_script_uri = "dfsdfs"
    assert utils.add_jumpstart_uri_tags(
        tags=tags,
        training_model_uri=training_model_uri,
        training_script_uri=training_script_uri,
    ) == [
        {"Key": "some", "Value": "tag"},
        {"Key": JumpStartTag.TRAINING_MODEL_URI.value, "Value": training_model_uri},
    ]

    tags = None
    training_script_uri = random_jumpstart_s3_uri("random_key")
    training_model_uri = "dfsdfs"
    assert utils.add_jumpstart_uri_tags(
        tags=tags,
        training_model_uri=training_model_uri,
        training_script_uri=training_script_uri,
    ) == [{"Key": JumpStartTag.TRAINING_SCRIPT_URI.value, "Value": training_script_uri}]

    tags = []
    training_script_uri = random_jumpstart_s3_uri("random_key")
    training_model_uri = "dfsdfs"
    assert utils.add_jumpstart_uri_tags(
        tags=tags,
        training_model_uri=training_model_uri,
        training_script_uri=training_script_uri,
    ) == [{"Key": JumpStartTag.TRAINING_SCRIPT_URI.value, "Value": training_script_uri}]

    tags = [{"Key": "some", "Value": "tag"}]
    training_script_uri = random_jumpstart_s3_uri("random_key")
    training_model_uri = "dfsdfs"
    assert utils.add_jumpstart_uri_tags(
        tags=tags,
        training_model_uri=training_model_uri,
        training_script_uri=training_script_uri,
    ) == [
        {"Key": "some", "Value": "tag"},
        {"Key": JumpStartTag.TRAINING_SCRIPT_URI.value, "Value": training_script_uri},
    ]

    tags = None
    training_script_uri = random_jumpstart_s3_uri("random_key")
    training_model_uri = random_jumpstart_s3_uri("random_key")
    assert utils.add_jumpstart_uri_tags(
        tags=tags,
        training_model_uri=training_model_uri,
        training_script_uri=training_script_uri,
    ) == [
        {
            "Key": JumpStartTag.TRAINING_MODEL_URI.value,
            "Value": training_model_uri,
        },
        {"Key": JumpStartTag.TRAINING_SCRIPT_URI.value, "Value": training_script_uri},
    ]

    tags = []
    training_script_uri = random_jumpstart_s3_uri("random_key")
    training_model_uri = random_jumpstart_s3_uri("random_key")
    assert utils.add_jumpstart_uri_tags(
        tags=tags,
        training_model_uri=training_model_uri,
        training_script_uri=training_script_uri,
    ) == [
        {
            "Key": JumpStartTag.TRAINING_MODEL_URI.value,
            "Value": training_model_uri,
        },
        {"Key": JumpStartTag.TRAINING_SCRIPT_URI.value, "Value": training_script_uri},
    ]

    tags = [{"Key": "some", "Value": "tag"}]
    training_script_uri = random_jumpstart_s3_uri("random_key")
    training_model_uri = random_jumpstart_s3_uri("random_key")
    assert utils.add_jumpstart_uri_tags(
        tags=tags,
        training_model_uri=training_model_uri,
        training_script_uri=training_script_uri,
    ) == [
        {"Key": "some", "Value": "tag"},
        {
            "Key": JumpStartTag.TRAINING_MODEL_URI.value,
            "Value": training_model_uri,
        },
        {"Key": JumpStartTag.TRAINING_SCRIPT_URI.value, "Value": training_script_uri},
    ]

    tags = [{"Key": JumpStartTag.TRAINING_MODEL_URI.value, "Value": "garbage-value"}]
    training_script_uri = random_jumpstart_s3_uri("random_key")
    training_model_uri = random_jumpstart_s3_uri("random_key")
    assert utils.add_jumpstart_uri_tags(
        tags=tags,
        training_model_uri=training_model_uri,
        training_script_uri=training_script_uri,
    ) == [
        {"Key": JumpStartTag.TRAINING_MODEL_URI.value, "Value": "garbage-value"},
        {"Key": JumpStartTag.TRAINING_SCRIPT_URI.value, "Value": training_script_uri},
    ]

    tags = [{"Key": JumpStartTag.TRAINING_SCRIPT_URI.value, "Value": "garbage-value"}]
    training_script_uri = random_jumpstart_s3_uri("random_key")
    training_model_uri = random_jumpstart_s3_uri("random_key")
    assert utils.add_jumpstart_uri_tags(
        tags=tags,
        training_model_uri=training_model_uri,
        training_script_uri=training_script_uri,
    ) == [
        {"Key": JumpStartTag.TRAINING_SCRIPT_URI.value, "Value": "garbage-value"},
        {"Key": JumpStartTag.TRAINING_MODEL_URI.value, "Value": training_model_uri},
    ]

    tags = [
        {"Key": JumpStartTag.TRAINING_SCRIPT_URI.value, "Value": "garbage-value"},
        {"Key": JumpStartTag.TRAINING_MODEL_URI.value, "Value": "garbage-value-2"},
    ]
    training_script_uri = random_jumpstart_s3_uri("random_key")
    training_model_uri = random_jumpstart_s3_uri("random_key")
    assert utils.add_jumpstart_uri_tags(
        tags=tags,
        training_model_uri=training_model_uri,
        training_script_uri=training_script_uri,
    ) == [
        {"Key": JumpStartTag.TRAINING_SCRIPT_URI.value, "Value": "garbage-value"},
        {"Key": JumpStartTag.TRAINING_MODEL_URI.value, "Value": "garbage-value-2"},
    ]


def test_update_inference_tags_with_jumpstart_training_script_tags():

    random_tag_1 = {"Key": "tag-key-1", "Value": "tag-val-1"}
    random_tag_2 = {"Key": "tag-key-2", "Value": "tag-val-2"}

    js_tag = {"Key": JumpStartTag.TRAINING_SCRIPT_URI.value, "Value": "garbage-value"}
    js_tag_2 = {"Key": JumpStartTag.TRAINING_SCRIPT_URI.value, "Value": "garbage-value-2"}

    assert [random_tag_2] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[random_tag_2], training_tags=None
    )

    assert [random_tag_2] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[random_tag_2], training_tags=[]
    )

    assert [random_tag_2] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[random_tag_2], training_tags=[random_tag_1]
    )

    assert [random_tag_2, js_tag] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[random_tag_2], training_tags=[random_tag_1, js_tag]
    )

    assert [random_tag_2, js_tag_2] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[random_tag_2, js_tag_2], training_tags=[random_tag_1, js_tag]
    )

    assert [] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[], training_tags=None
    )

    assert [] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[], training_tags=[]
    )

    assert [] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[], training_tags=[random_tag_1]
    )

    assert [js_tag] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[], training_tags=[random_tag_1, js_tag]
    )

    assert None is utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=None, training_tags=None
    )

    assert None is utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=None, training_tags=[]
    )

    assert None is utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=None, training_tags=[random_tag_1]
    )

    assert [js_tag] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=None, training_tags=[random_tag_1, js_tag]
    )


def test_update_inference_tags_with_jumpstart_training_model_tags():

    random_tag_1 = {"Key": "tag-key-1", "Value": "tag-val-1"}
    random_tag_2 = {"Key": "tag-key-2", "Value": "tag-val-2"}

    js_tag = {"Key": JumpStartTag.TRAINING_MODEL_URI.value, "Value": "garbage-value"}
    js_tag_2 = {"Key": JumpStartTag.TRAINING_MODEL_URI.value, "Value": "garbage-value-2"}

    assert [random_tag_2] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[random_tag_2], training_tags=None
    )

    assert [random_tag_2] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[random_tag_2], training_tags=[]
    )

    assert [random_tag_2] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[random_tag_2], training_tags=[random_tag_1]
    )

    assert [random_tag_2, js_tag] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[random_tag_2], training_tags=[random_tag_1, js_tag]
    )

    assert [random_tag_2, js_tag_2] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[random_tag_2, js_tag_2], training_tags=[random_tag_1, js_tag]
    )

    assert [] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[], training_tags=None
    )

    assert [] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[], training_tags=[]
    )

    assert [] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[], training_tags=[random_tag_1]
    )

    assert [js_tag] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[], training_tags=[random_tag_1, js_tag]
    )

    assert None is utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=None, training_tags=None
    )

    assert None is utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=None, training_tags=[]
    )

    assert None is utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=None, training_tags=[random_tag_1]
    )

    assert [js_tag] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=None, training_tags=[random_tag_1, js_tag]
    )


def test_update_inference_tags_with_jumpstart_training_script_tags_inference():

    random_tag_1 = {"Key": "tag-key-1", "Value": "tag-val-1"}
    random_tag_2 = {"Key": "tag-key-2", "Value": "tag-val-2"}

    js_tag = {"Key": JumpStartTag.INFERENCE_SCRIPT_URI.value, "Value": "garbage-value"}
    js_tag_2 = {"Key": JumpStartTag.INFERENCE_SCRIPT_URI.value, "Value": "garbage-value-2"}

    assert [random_tag_2] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[random_tag_2], training_tags=None
    )

    assert [random_tag_2] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[random_tag_2], training_tags=[]
    )

    assert [random_tag_2] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[random_tag_2], training_tags=[random_tag_1]
    )

    assert [random_tag_2, js_tag] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[random_tag_2], training_tags=[random_tag_1, js_tag]
    )

    assert [random_tag_2, js_tag_2] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[random_tag_2, js_tag_2], training_tags=[random_tag_1, js_tag]
    )

    assert [] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[], training_tags=None
    )

    assert [] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[], training_tags=[]
    )

    assert [] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[], training_tags=[random_tag_1]
    )

    assert [js_tag] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[], training_tags=[random_tag_1, js_tag]
    )

    assert None is utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=None, training_tags=None
    )

    assert None is utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=None, training_tags=[]
    )

    assert None is utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=None, training_tags=[random_tag_1]
    )

    assert [js_tag] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=None, training_tags=[random_tag_1, js_tag]
    )


def test_update_inference_tags_with_jumpstart_training_model_tags_inference():

    random_tag_1 = {"Key": "tag-key-1", "Value": "tag-val-1"}
    random_tag_2 = {"Key": "tag-key-2", "Value": "tag-val-2"}

    js_tag = {"Key": JumpStartTag.INFERENCE_MODEL_URI.value, "Value": "garbage-value"}
    js_tag_2 = {"Key": JumpStartTag.INFERENCE_MODEL_URI.value, "Value": "garbage-value-2"}

    assert [random_tag_2] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[random_tag_2], training_tags=None
    )

    assert [random_tag_2] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[random_tag_2], training_tags=[]
    )

    assert [random_tag_2] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[random_tag_2], training_tags=[random_tag_1]
    )

    assert [random_tag_2, js_tag] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[random_tag_2], training_tags=[random_tag_1, js_tag]
    )

    assert [random_tag_2, js_tag_2] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[random_tag_2, js_tag_2], training_tags=[random_tag_1, js_tag]
    )

    assert [] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[], training_tags=None
    )

    assert [] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[], training_tags=[]
    )

    assert [] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[], training_tags=[random_tag_1]
    )

    assert [js_tag] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=[], training_tags=[random_tag_1, js_tag]
    )

    assert None is utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=None, training_tags=None
    )

    assert None is utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=None, training_tags=[]
    )

    assert None is utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=None, training_tags=[random_tag_1]
    )

    assert [js_tag] == utils.update_inference_tags_with_jumpstart_training_tags(
        inference_tags=None, training_tags=[random_tag_1, js_tag]
    )


@patch("sagemaker.jumpstart.utils.accessors.JumpStartModelsAccessor._get_manifest")
def test_jumpstart_accept_eula_logs(mock_get_manifest):
    mock_get_manifest.return_value = []

    def make_accept_eula_inference_spec(*largs, **kwargs):
        spec = get_spec_from_base_spec(model_id="pytorch-eqa-bert-base-cased", version="*")
        spec.hosting_eula_key = "read/the/fine/print.txt"
        return spec

    with patch("logging.Logger.info") as mocked_info_log:
        utils.emit_logs_based_on_model_specs(
            make_accept_eula_inference_spec(), "us-east-1", MOCK_CLIENT
        )
        mocked_info_log.assert_any_call(
            "Model 'pytorch-eqa-bert-base-cased' requires accepting end-user license agreement (EULA). "
            "See https://jumpstart-cache-prod-us-east-1.s3.us-east-1.amazonaws.com/read/the/fine/print.txt"
            " for terms of use.",
        )


@patch("sagemaker.jumpstart.utils.accessors.JumpStartModelsAccessor._get_manifest")
def test_jumpstart_vulnerable_model_warnings(mock_get_manifest):
    mock_get_manifest.return_value = []

    def make_vulnerable_inference_spec(*largs, **kwargs):
        spec = get_spec_from_base_spec(model_id="pytorch-eqa-bert-base-cased", version="*")
        spec.inference_vulnerable = True
        spec.inference_vulnerabilities = ["some", "vulnerability"]
        return spec

    with patch("logging.Logger.warning") as mocked_warning_log:
        utils.emit_logs_based_on_model_specs(
            make_vulnerable_inference_spec(), "us-west-2", MOCK_CLIENT
        )
        mocked_warning_log.assert_called_once_with(
            "Using vulnerable JumpStart model '%s' and version '%s'.",
            "pytorch-eqa-bert-base-cased",
            "*",
        )


@patch("sagemaker.jumpstart.utils.accessors.JumpStartModelsAccessor._get_manifest")
def test_jumpstart_old_model_spec(mock_get_manifest):

    mock_get_manifest.return_value = [
        JumpStartModelHeader(
            {
                "model_id": "tensorflow-ic-imagenet-inception-v3-classification-4",
                "version": "1.1.0",
                "min_version": "2.49.0",
                "spec_key": "community_models_specs/tensorflow-ic-imagenet-in"
                "ception-v3-classification-4/specs_v1.1.0.json",
            }
        ),
        JumpStartModelHeader(
            {
                "model_id": "tensorflow-ic-imagenet-inception-v3-classification-4",
                "version": "1.0.0",
                "min_version": "2.49.0",
                "spec_key": "community_models_specs/tensorflow-ic-imagenet-"
                "inception-v3-classification-4/specs_v1.0.0.json",
            }
        ),
    ]

    with patch("logging.Logger.info") as mocked_info_log:
        utils.emit_logs_based_on_model_specs(
            get_spec_from_base_spec(
                model_id="tensorflow-ic-imagenet-inception-v3-classification-4", version="1.0.0"
            ),
            "us-west-2",
            MOCK_CLIENT,
        )

        mocked_info_log.assert_called_once_with(
            "Using model 'tensorflow-ic-imagenet-inception-v3-classification-4' with version '1.0.0'. "
            "You can upgrade to version '1.1.0' to get the latest model specifications. Note that models "
            "may have different input/output signatures after a major version upgrade."
        )

        mocked_info_log.reset_mock()

        utils.emit_logs_based_on_model_specs(
            get_spec_from_base_spec(
                model_id="tensorflow-ic-imagenet-inception-v3-classification-4", version="1.1.0"
            ),
            "us-west-2",
            MOCK_CLIENT,
        )

        mocked_info_log.assert_not_called()


@patch("sagemaker.jumpstart.utils.accessors.JumpStartModelsAccessor._get_manifest")
def test_jumpstart_deprecated_model_warnings(mock_get_manifest):
    mock_get_manifest.return_value = []

    def make_deprecated_spec(*largs, **kwargs):
        spec = get_spec_from_base_spec(model_id="pytorch-eqa-bert-base-cased", version="*")
        spec.deprecated = True
        return spec

    with patch("logging.Logger.warning") as mocked_warning_log:
        utils.emit_logs_based_on_model_specs(make_deprecated_spec(), "us-west-2", MOCK_CLIENT)

        mocked_warning_log.assert_called_once_with(
            "Using deprecated JumpStart model 'pytorch-eqa-bert-base-cased' and version '*'."
        )

    deprecated_message = "this model is deprecated"

    def make_deprecated_message_spec(*largs, **kwargs):
        spec = get_spec_from_base_spec(model_id="pytorch-eqa-bert-base-cased", version="*")
        spec.deprecated_message = deprecated_message
        spec.deprecated = True
        return spec

    with patch("logging.Logger.warning") as mocked_warning_log:
        utils.emit_logs_based_on_model_specs(
            make_deprecated_message_spec(), "us-west-2", MOCK_CLIENT
        )

        mocked_warning_log.assert_called_once_with(deprecated_message)

    deprecate_warn_message = "warn-msg"

    def make_deprecated_warning_message_spec(*largs, **kwargs):
        spec = get_spec_from_base_spec(model_id="pytorch-eqa-bert-base-cased", version="*")
        spec.deprecate_warn_message = deprecate_warn_message
        return spec

    with patch("logging.Logger.warning") as mocked_warning_log:
        utils.emit_logs_based_on_model_specs(
            make_deprecated_warning_message_spec(), "us-west-2", MOCK_CLIENT
        )
        mocked_warning_log.assert_called_once_with(
            deprecate_warn_message,
        )


@patch("sagemaker.jumpstart.utils.accessors.JumpStartModelsAccessor._get_manifest")
def test_jumpstart_usage_info_message(mock_get_manifest):
    mock_get_manifest.return_value = []

    usage_info_message = "This model might change your life."

    def make_info_spec(*largs, **kwargs):
        spec = get_spec_from_base_spec(model_id="pytorch-eqa-bert-base-cased", version="*")
        spec.usage_info_message = usage_info_message
        return spec

    with patch("logging.Logger.info") as mocked_info_log:
        utils.emit_logs_based_on_model_specs(make_info_spec(), "us-west-2", MOCK_CLIENT)

        mocked_info_log.assert_called_with(usage_info_message)


@patch("sagemaker.jumpstart.accessors.JumpStartModelsAccessor.get_model_specs")
def test_jumpstart_vulnerable_model_errors(patched_get_model_specs):
    def make_vulnerable_inference_spec(*largs, **kwargs):
        spec = get_spec_from_base_spec(*largs, **kwargs)
        spec.inference_vulnerable = True
        spec.inference_vulnerabilities = ["some", "vulnerability"]
        return spec

    patched_get_model_specs.side_effect = make_vulnerable_inference_spec

    with pytest.raises(VulnerableJumpStartModelError) as e:
        utils.verify_model_region_and_return_specs(
            model_id="pytorch-eqa-bert-base-cased",
            version="*",
            scope=JumpStartScriptScope.INFERENCE.value,
            region="us-west-2",
        )
    assert (
        "Version '*' of JumpStart model 'pytorch-eqa-bert-base-cased' has at least 1 "
        "vulnerable dependency in the inference script. "
        "We recommend that you specify a more recent model version or "
        "choose a different model. To access the "
        "latest models and model versions, be sure to upgrade "
        "to the latest version of the SageMaker Python SDK. "
        "List of vulnerabilities: some, vulnerability"
    ) == str(e.value.message)

    def make_vulnerable_training_spec(*largs, **kwargs):
        spec = get_spec_from_base_spec(*largs, **kwargs)
        spec.training_vulnerable = True
        spec.training_vulnerabilities = ["some", "vulnerability"]
        return spec

    patched_get_model_specs.side_effect = make_vulnerable_training_spec

    with pytest.raises(VulnerableJumpStartModelError) as e:
        utils.verify_model_region_and_return_specs(
            model_id="pytorch-eqa-bert-base-cased",
            version="*",
            scope=JumpStartScriptScope.TRAINING.value,
            region="us-west-2",
        )
    assert (
        "Version '*' of JumpStart model 'pytorch-eqa-bert-base-cased' has at least 1 "
        "vulnerable dependency in the training script. "
        "We recommend that you specify a more recent model version or "
        "choose a different model. To access the "
        "latest models and model versions, be sure to upgrade "
        "to the latest version of the SageMaker Python SDK. "
        "List of vulnerabilities: some, vulnerability"
    ) == str(e.value.message)


@patch("sagemaker.jumpstart.accessors.JumpStartModelsAccessor.get_model_specs")
def test_jumpstart_deprecated_model_errors(patched_get_model_specs):
    def make_deprecated_spec(*largs, **kwargs):
        spec = get_spec_from_base_spec(*largs, **kwargs)
        spec.deprecated = True
        return spec

    patched_get_model_specs.side_effect = make_deprecated_spec

    with pytest.raises(DeprecatedJumpStartModelError) as e:
        utils.verify_model_region_and_return_specs(
            model_id="pytorch-eqa-bert-base-cased",
            version="*",
            scope=JumpStartScriptScope.INFERENCE.value,
            region="us-west-2",
        )
    assert "Version '*' of JumpStart model 'pytorch-eqa-bert-base-cased' is deprecated. "
    "Please try targeting a higher version of the model or using a different model." == str(
        e.value.message
    )

    deprecated_message = "this model is deprecated"

    def make_deprecated_message_spec(*largs, **kwargs):
        spec = get_spec_from_base_spec(*largs, **kwargs)
        spec.deprecated_message = deprecated_message
        spec.deprecated = True
        return spec

    patched_get_model_specs.side_effect = make_deprecated_message_spec

    with pytest.raises(DeprecatedJumpStartModelError) as e:
        utils.verify_model_region_and_return_specs(
            model_id="pytorch-eqa-bert-base-cased",
            version="*",
            scope=JumpStartScriptScope.INFERENCE.value,
            region="us-west-2",
        )
    assert deprecated_message == str(e.value.message)


def test_get_jumpstart_base_name_if_jumpstart_model():
    uris = [random_jumpstart_s3_uri("random_key") for _ in range(random.randint(1, 10))]
    assert JUMPSTART_RESOURCE_BASE_NAME == utils.get_jumpstart_base_name_if_jumpstart_model(*uris)

    uris = ["s3://not-jumpstart-bucket/some-key" for _ in range(random.randint(0, 10))]
    assert utils.get_jumpstart_base_name_if_jumpstart_model(*uris) is None

    uris = ["s3://not-jumpstart-bucket/some-key" for _ in range(random.randint(1, 10))] + [
        random_jumpstart_s3_uri("random_key")
    ]
    assert JUMPSTART_RESOURCE_BASE_NAME == utils.get_jumpstart_base_name_if_jumpstart_model(*uris)

    uris = (
        ["s3://not-jumpstart-bucket/some-key" for _ in range(random.randint(1, 10))]
        + [random_jumpstart_s3_uri("random_key")]
        + ["s3://not-jumpstart-bucket/some-key-2" for _ in range(random.randint(1, 10))]
    )
    assert JUMPSTART_RESOURCE_BASE_NAME == utils.get_jumpstart_base_name_if_jumpstart_model(*uris)


def test_mime_type_enum_from_str():
    mime_types = {elt.value for elt in MIMEType}

    suffixes = {"", "; ", ";fsdfsdfsdfsd", ";;;;;", ";sdfsafd;fdasfs;"}

    for mime_type in mime_types:
        for suffix in suffixes:
            mime_type_with_suffix = mime_type + suffix
            assert MIMEType.from_suffixed_type(mime_type_with_suffix) == mime_type


class TestIsValidModelId(TestCase):
    @patch("sagemaker.jumpstart.utils.accessors.JumpStartModelsAccessor._get_manifest")
    @patch("sagemaker.jumpstart.utils.accessors.JumpStartModelsAccessor.get_model_specs")
    def test_validate_model_id_and_get_type_open_weights(
        self,
        mock_get_model_specs: Mock,
        mock_get_manifest: Mock,
    ):
        mock_get_manifest.return_value = [
            Mock(model_id="ay"),
            Mock(model_id="bee"),
            Mock(model_id="see"),
        ]

        mock_session_value = DEFAULT_JUMPSTART_SAGEMAKER_SESSION
        mock_s3_client_value = mock_session_value.s3_client

        patched = partial(
            utils.validate_model_id_and_get_type, sagemaker_session=mock_session_value
        )

        with patch("sagemaker.jumpstart.utils.validate_model_id_and_get_type", patched):
            assert utils.validate_model_id_and_get_type("bee") == JumpStartModelType.OPEN_WEIGHTS
            mock_get_manifest.assert_called_with(
                region=JUMPSTART_DEFAULT_REGION_NAME,
                s3_client=mock_s3_client_value,
                model_type=JumpStartModelType.OPEN_WEIGHTS,
            )
            mock_get_model_specs.assert_not_called()

            mock_get_manifest.reset_mock()
            mock_get_model_specs.reset_mock()

            mock_get_manifest.return_value = [
                Mock(model_id="ay"),
                Mock(model_id="bee"),
                Mock(model_id="see"),
            ]

            mock_get_model_specs.return_value = Mock(training_supported=True)
            self.assertIsNone(
                utils.validate_model_id_and_get_type(
                    "invalid", script=JumpStartScriptScope.TRAINING
                )
            )
            assert (
                utils.validate_model_id_and_get_type("bee", script=JumpStartScriptScope.TRAINING)
                == JumpStartModelType.OPEN_WEIGHTS
            )

            mock_get_manifest.assert_called_with(
                region=JUMPSTART_DEFAULT_REGION_NAME,
                s3_client=mock_s3_client_value,
                model_type=JumpStartModelType.OPEN_WEIGHTS,
            )

    @patch("sagemaker.jumpstart.utils.accessors.JumpStartModelsAccessor._get_manifest")
    @patch("sagemaker.jumpstart.utils.accessors.JumpStartModelsAccessor.get_model_specs")
    def test_validate_model_id_and_get_type_invalid(
        self, mock_get_model_specs: Mock, mock_get_manifest: Mock
    ):
        mock_get_manifest.side_effect = (
            lambda region, model_type, *args, **kwargs: get_prototype_manifest(region, model_type)
        )

        mock_session_value = DEFAULT_JUMPSTART_SAGEMAKER_SESSION
        mock_s3_client_value = mock_session_value.s3_client

        patched = partial(
            utils.validate_model_id_and_get_type, sagemaker_session=mock_session_value
        )

        with patch("sagemaker.jumpstart.utils.validate_model_id_and_get_type", patched):

            self.assertIsNone(utils.validate_model_id_and_get_type("dee"))
            self.assertIsNone(utils.validate_model_id_and_get_type(""))
            self.assertIsNone(utils.validate_model_id_and_get_type(None))
            self.assertIsNone(utils.validate_model_id_and_get_type(set()))

            mock_get_manifest.assert_called()

            mock_get_model_specs.assert_not_called()

            mock_get_manifest.reset_mock()
            mock_get_model_specs.reset_mock()

            assert (
                utils.validate_model_id_and_get_type("ai21-summarization")
                == JumpStartModelType.PROPRIETARY
            )
            self.assertIsNone(utils.validate_model_id_and_get_type("ai21-summarization-2"))

            mock_get_manifest.assert_called_with(
                region=JUMPSTART_DEFAULT_REGION_NAME,
                s3_client=mock_s3_client_value,
                model_type=JumpStartModelType.PROPRIETARY,
            )

            self.assertIsNone(
                utils.validate_model_id_and_get_type("dee", script=JumpStartScriptScope.TRAINING)
            )
            self.assertIsNone(
                utils.validate_model_id_and_get_type("", script=JumpStartScriptScope.TRAINING)
            )
            self.assertIsNone(
                utils.validate_model_id_and_get_type(None, script=JumpStartScriptScope.TRAINING)
            )
            self.assertIsNone(
                utils.validate_model_id_and_get_type(set(), script=JumpStartScriptScope.TRAINING)
            )

            assert (
                utils.validate_model_id_and_get_type("pytorch-eqa-bert-base-cased")
                == JumpStartModelType.OPEN_WEIGHTS
            )
            mock_get_manifest.assert_called_with(
                region=JUMPSTART_DEFAULT_REGION_NAME,
                s3_client=mock_s3_client_value,
                model_type=JumpStartModelType.OPEN_WEIGHTS,
            )

        with pytest.raises(ValueError):
            utils.validate_model_id_and_get_type(
                "ai21-summarization", script=JumpStartScriptScope.TRAINING
            )


class TestGetModelIdVersionFromResourceArn(TestCase):
    def test_no_model_id_no_version_found(self):
        mock_list_tags = Mock()
        mock_sagemaker_session = Mock()
        mock_sagemaker_session.list_tags = mock_list_tags
        mock_list_tags.return_value = [{"Key": "blah", "Value": "blah1"}]

        self.assertEquals(
            utils.get_jumpstart_model_id_version_from_resource_arn(
                "some-arn", mock_sagemaker_session
            ),
            (None, None, None),
        )
        mock_list_tags.assert_called_once_with("some-arn")

    def test_model_id_no_version_found(self):
        mock_list_tags = Mock()
        mock_sagemaker_session = Mock()
        mock_sagemaker_session.list_tags = mock_list_tags
        mock_list_tags.return_value = [
            {"Key": "blah", "Value": "blah1"},
            {"Key": JumpStartTag.MODEL_ID, "Value": "model_id"},
        ]

        self.assertEquals(
            utils.get_jumpstart_model_id_version_from_resource_arn(
                "some-arn", mock_sagemaker_session
            ),
            ("model_id", None, None),
        )
        mock_list_tags.assert_called_once_with("some-arn")

    def test_no_model_id_version_found(self):
        mock_list_tags = Mock()
        mock_sagemaker_session = Mock()
        mock_sagemaker_session.list_tags = mock_list_tags
        mock_list_tags.return_value = [
            {"Key": "blah", "Value": "blah1"},
            {"Key": JumpStartTag.MODEL_VERSION, "Value": "model_version"},
        ]

        self.assertEquals(
            utils.get_jumpstart_model_id_version_from_resource_arn(
                "some-arn", mock_sagemaker_session
            ),
            (None, "model_version", None),
        )
        mock_list_tags.assert_called_once_with("some-arn")

    def test_no_config_name_found(self):
        mock_list_tags = Mock()
        mock_sagemaker_session = Mock()
        mock_sagemaker_session.list_tags = mock_list_tags
        mock_list_tags.return_value = [{"Key": "blah", "Value": "blah1"}]

        self.assertEquals(
            utils.get_jumpstart_model_id_version_from_resource_arn(
                "some-arn", mock_sagemaker_session
            ),
            (None, None, None),
        )
        mock_list_tags.assert_called_once_with("some-arn")

    def test_config_name_found(self):
        mock_list_tags = Mock()
        mock_sagemaker_session = Mock()
        mock_sagemaker_session.list_tags = mock_list_tags
        mock_list_tags.return_value = [
            {"Key": "blah", "Value": "blah1"},
            {"Key": JumpStartTag.MODEL_CONFIG_NAME, "Value": "config_name"},
        ]

        self.assertEquals(
            utils.get_jumpstart_model_id_version_from_resource_arn(
                "some-arn", mock_sagemaker_session
            ),
            (None, None, "config_name"),
        )
        mock_list_tags.assert_called_once_with("some-arn")

    def test_model_id_version_found(self):
        mock_list_tags = Mock()
        mock_sagemaker_session = Mock()
        mock_sagemaker_session.list_tags = mock_list_tags
        mock_list_tags.return_value = [
            {"Key": "blah", "Value": "blah1"},
            {"Key": JumpStartTag.MODEL_ID, "Value": "model_id"},
            {"Key": JumpStartTag.MODEL_VERSION, "Value": "model_version"},
        ]

        self.assertEquals(
            utils.get_jumpstart_model_id_version_from_resource_arn(
                "some-arn", mock_sagemaker_session
            ),
            ("model_id", "model_version", None),
        )
        mock_list_tags.assert_called_once_with("some-arn")

    def test_multiple_model_id_versions_found(self):
        mock_list_tags = Mock()
        mock_sagemaker_session = Mock()
        mock_sagemaker_session.list_tags = mock_list_tags
        mock_list_tags.return_value = [
            {"Key": "blah", "Value": "blah1"},
            {"Key": JumpStartTag.MODEL_ID, "Value": "model_id_1"},
            {"Key": JumpStartTag.MODEL_VERSION, "Value": "model_version_1"},
            {"Key": JumpStartTag.MODEL_ID, "Value": "model_id_2"},
            {"Key": JumpStartTag.MODEL_VERSION, "Value": "model_version_2"},
        ]

        self.assertEquals(
            utils.get_jumpstart_model_id_version_from_resource_arn(
                "some-arn", mock_sagemaker_session
            ),
            (None, None, None),
        )
        mock_list_tags.assert_called_once_with("some-arn")

    def test_multiple_model_id_versions_found_aliases_consistent(self):
        mock_list_tags = Mock()
        mock_sagemaker_session = Mock()
        mock_sagemaker_session.list_tags = mock_list_tags
        mock_list_tags.return_value = [
            {"Key": "blah", "Value": "blah1"},
            {"Key": JumpStartTag.MODEL_ID, "Value": "model_id_1"},
            {"Key": JumpStartTag.MODEL_VERSION, "Value": "model_version_1"},
            {"Key": random.choice(EXTRA_MODEL_ID_TAGS), "Value": "model_id_1"},
            {"Key": random.choice(EXTRA_MODEL_VERSION_TAGS), "Value": "model_version_1"},
        ]

        self.assertEquals(
            utils.get_jumpstart_model_id_version_from_resource_arn(
                "some-arn", mock_sagemaker_session
            ),
            ("model_id_1", "model_version_1", None),
        )
        mock_list_tags.assert_called_once_with("some-arn")

    def test_multiple_model_id_versions_found_aliases_inconsistent(self):
        mock_list_tags = Mock()
        mock_sagemaker_session = Mock()
        mock_sagemaker_session.list_tags = mock_list_tags
        mock_list_tags.return_value = [
            {"Key": "blah", "Value": "blah1"},
            {"Key": JumpStartTag.MODEL_ID, "Value": "model_id_1"},
            {"Key": JumpStartTag.MODEL_VERSION, "Value": "model_version_1"},
            {"Key": random.choice(EXTRA_MODEL_ID_TAGS), "Value": "model_id_2"},
            {"Key": random.choice(EXTRA_MODEL_VERSION_TAGS), "Value": "model_version_2"},
        ]

        self.assertEquals(
            utils.get_jumpstart_model_id_version_from_resource_arn(
                "some-arn", mock_sagemaker_session
            ),
            (None, None, None),
        )
        mock_list_tags.assert_called_once_with("some-arn")

    def test_multiple_config_names_found_aliases_inconsistent(self):
        mock_list_tags = Mock()
        mock_sagemaker_session = Mock()
        mock_sagemaker_session.list_tags = mock_list_tags
        mock_list_tags.return_value = [
            {"Key": "blah", "Value": "blah1"},
            {"Key": JumpStartTag.MODEL_ID, "Value": "model_id_1"},
            {"Key": JumpStartTag.MODEL_VERSION, "Value": "model_version_1"},
            {"Key": JumpStartTag.MODEL_CONFIG_NAME, "Value": "config_name_1"},
            {"Key": JumpStartTag.MODEL_CONFIG_NAME, "Value": "config_name_2"},
        ]

        self.assertEquals(
            utils.get_jumpstart_model_id_version_from_resource_arn(
                "some-arn", mock_sagemaker_session
            ),
            ("model_id_1", "model_version_1", None),
        )
        mock_list_tags.assert_called_once_with("some-arn")


class TestJumpStartLogger(TestCase):
    @patch.dict("os.environ", {})
    @patch("logging.StreamHandler.emit")
    @patch("sagemaker.jumpstart.constants.JUMPSTART_LOGGER.propagate", False)
    def test_logger_normal_mode(self, mocked_emit: Mock):

        JUMPSTART_LOGGER.warning("Self destruct in 3...2...1...")

        mocked_emit.assert_called_once()

    @patch.dict("os.environ", {ENV_VARIABLE_DISABLE_JUMPSTART_LOGGING: "true"})
    @patch("logging.StreamHandler.emit")
    @patch("sagemaker.jumpstart.constants.JUMPSTART_LOGGER.propagate", False)
    def test_logger_disabled(self, mocked_emit: Mock):

        JUMPSTART_LOGGER.warning("Self destruct in 3...2...1...")

        mocked_emit.assert_not_called()


@pytest.mark.parametrize(
    "s3_bucket_name, s3_client, sagemaker_session, region",
    [
        (
            "jumpstart-cache-prod",
            boto3.client("s3", region_name="blah-blah"),
            session.Session(boto3.Session(region_name="blah-blah")),
            JUMPSTART_DEFAULT_REGION_NAME,
        ),
        (
            "jumpstart-cache-prod-us-west-2",
            boto3.client("s3", region_name="us-west-2"),
            session.Session(boto3.Session(region_name="us-west-2")),
            "us-west-2",
        ),
        ("jumpstart-cache-prod", boto3.client("s3", region_name="us-east-2"), None, "us-east-2"),
    ],
)
def test_get_region_fallback_success(s3_bucket_name, s3_client, sagemaker_session, region):
    assert region == utils.get_region_fallback(s3_bucket_name, s3_client, sagemaker_session)


@pytest.mark.parametrize(
    "s3_bucket_name, s3_client, sagemaker_session",
    [
        (
            "jumpstart-cache-prod-us-west-2",
            boto3.client("s3", region_name="us-east-2"),
            session.Session(boto3.Session(region_name="us-west-2")),
        ),
        (
            "jumpstart-cache-prod-us-west-2",
            boto3.client("s3", region_name="us-west-2"),
            session.Session(boto3.Session(region_name="eu-north-1")),
        ),
        (
            "jumpstart-cache-prod-us-west-2-us-east-2",
            boto3.client("s3", region_name="us-east-2"),
            None,
        ),
    ],
)
def test_get_region_fallback_failure(s3_bucket_name, s3_client, sagemaker_session):
    with pytest.raises(ValueError):
        utils.get_region_fallback(s3_bucket_name, s3_client, sagemaker_session)


class TestConfigs:
    @patch("sagemaker.jumpstart.accessors.JumpStartModelsAccessor.get_model_specs")
    def test_get_jumpstart_config_names_empty(
        self,
        patched_get_model_specs,
    ):

        patched_get_model_specs.side_effect = get_special_model_spec

        assert utils.get_config_names("mock-region", "gemma-model", "mock-model-version") == []

    @patch("sagemaker.jumpstart.accessors.JumpStartModelsAccessor.get_model_specs")
    def test_get_jumpstart_config_names_success(
        self,
        patched_get_model_specs,
    ):
        patched_get_model_specs.side_effect = get_base_spec_with_prototype_configs

        assert utils.get_config_names("mock-region", "mock-model", "mock-model-version") == [
            "neuron-inference",
            "neuron-inference-budget",
            "gpu-inference-budget",
            "gpu-inference",
        ]

    @patch("sagemaker.jumpstart.accessors.JumpStartModelsAccessor.get_model_specs")
    def test_get_jumpstart_config_names_training(
        self,
        patched_get_model_specs,
    ):
        patched_get_model_specs.side_effect = get_base_spec_with_prototype_configs

        assert utils.get_config_names(
            "mock-region", "mock-model", "mock-model-version", scope=JumpStartScriptScope.TRAINING
        ) == ["neuron-training", "neuron-training-budget", "gpu-training", "gpu-training-budget"]

    @patch("sagemaker.jumpstart.accessors.JumpStartModelsAccessor.get_model_specs")
    def test_get_jumpstart_configs_empty(
        self,
        patched_get_model_specs,
    ):
        patched_get_model_specs.side_effect = get_special_model_spec

        assert (
            utils.get_jumpstart_configs(
                "mock-region", "gemma-model", "mock-model-version", config_names=["gpu-inference"]
            )
            == {}
        )

    @patch("sagemaker.jumpstart.accessors.JumpStartModelsAccessor.get_model_specs")
    def test_get_jumpstart_configs_success(
        self,
        patched_get_model_specs,
    ):
        patched_get_model_specs.side_effect = get_base_spec_with_prototype_configs

        configs = utils.get_jumpstart_configs(
            "mock-region", "mock-model", "mock-model-version", config_names=["gpu-inference"]
        )
        assert configs.keys() == {"gpu-inference"}

        config = configs["gpu-inference"]
        assert config.base_fields["model_id"] == "pytorch-ic-mobilenet-v2"
        assert config.resolved_config["supported_inference_instance_types"] == [
            "ml.p2.xlarge",
            "ml.p3.2xlarge",
        ]


class TestBenchmarkStats:
    @patch("sagemaker.jumpstart.accessors.JumpStartModelsAccessor.get_model_specs")
    def test_get_jumpstart_benchmark_stats_empty(
        self,
        patched_get_model_specs,
    ):

        patched_get_model_specs.side_effect = get_special_model_spec

        assert utils.get_benchmark_stats("mock-region", "gemma-model", "mock-model-version") == {}

    @patch("sagemaker.jumpstart.accessors.JumpStartModelsAccessor.get_model_specs")
    def test_get_jumpstart_benchmark_stats_full_list(
        self,
        patched_get_model_specs,
    ):
        patched_get_model_specs.side_effect = get_base_spec_with_prototype_configs

        assert utils.get_benchmark_stats(
            "mock-region", "mock-model", "mock-model-version", config_names=None
        ) == {
            "neuron-inference": {
                "ml.inf2.2xlarge": [
                    JumpStartBenchmarkStat({"name": "Latency", "value": "100", "unit": "Tokens/S"})
                ]
            },
            "neuron-inference-budget": {
                "ml.inf2.2xlarge": [
                    JumpStartBenchmarkStat({"name": "Latency", "value": "100", "unit": "Tokens/S"})
                ]
            },
            "gpu-inference-budget": {
                "ml.p3.2xlarge": [
                    JumpStartBenchmarkStat({"name": "Latency", "value": "100", "unit": "Tokens/S"})
                ]
            },
            "gpu-inference": {
                "ml.p3.2xlarge": [
                    JumpStartBenchmarkStat({"name": "Latency", "value": "100", "unit": "Tokens/S"})
                ]
            },
        }

    @patch("sagemaker.jumpstart.accessors.JumpStartModelsAccessor.get_model_specs")
    def test_get_jumpstart_benchmark_stats_partial_list(
        self,
        patched_get_model_specs,
    ):
        patched_get_model_specs.side_effect = get_base_spec_with_prototype_configs

        assert utils.get_benchmark_stats(
            "mock-region",
            "mock-model",
            "mock-model-version",
            config_names=["neuron-inference-budget", "gpu-inference-budget"],
        ) == {
            "neuron-inference-budget": {
                "ml.inf2.2xlarge": [
                    JumpStartBenchmarkStat({"name": "Latency", "value": "100", "unit": "Tokens/S"})
                ]
            },
            "gpu-inference-budget": {
                "ml.p3.2xlarge": [
                    JumpStartBenchmarkStat({"name": "Latency", "value": "100", "unit": "Tokens/S"})
                ]
            },
        }

    @patch("sagemaker.jumpstart.accessors.JumpStartModelsAccessor.get_model_specs")
    def test_get_jumpstart_benchmark_stats_single_stat(
        self,
        patched_get_model_specs,
    ):
        patched_get_model_specs.side_effect = get_base_spec_with_prototype_configs

        assert utils.get_benchmark_stats(
            "mock-region",
            "mock-model",
            "mock-model-version",
            config_names=["neuron-inference-budget"],
        ) == {
            "neuron-inference-budget": {
                "ml.inf2.2xlarge": [
                    JumpStartBenchmarkStat({"name": "Latency", "value": "100", "unit": "Tokens/S"})
                ]
            }
        }

    @patch("sagemaker.jumpstart.accessors.JumpStartModelsAccessor.get_model_specs")
    def test_get_jumpstart_benchmark_stats_invalid_names(
        self,
        patched_get_model_specs,
    ):
        patched_get_model_specs.side_effect = get_base_spec_with_prototype_configs

        with pytest.raises(ValueError) as e:
            utils.get_benchmark_stats(
                "mock-region",
                "mock-model",
                "mock-model-version",
                config_names=["invalid-conig-name"],
            )
            assert "Unknown config name: 'invalid-conig-name'" in str(e.value)

    @patch("sagemaker.jumpstart.accessors.JumpStartModelsAccessor.get_model_specs")
    def test_get_jumpstart_benchmark_stats_training(
        self,
        patched_get_model_specs,
    ):
        patched_get_model_specs.side_effect = get_base_spec_with_prototype_configs

        assert utils.get_benchmark_stats(
            "mock-region",
            "mock-model",
            "mock-model-version",
            scope=JumpStartScriptScope.TRAINING,
            config_names=["neuron-training", "gpu-training-budget"],
        ) == {
            "neuron-training": {
                "ml.tr1n1.2xlarge": [
                    JumpStartBenchmarkStat({"name": "Latency", "value": "100", "unit": "Tokens/S"})
                ],
                "ml.tr1n1.4xlarge": [
                    JumpStartBenchmarkStat({"name": "Latency", "value": "50", "unit": "Tokens/S"})
                ],
            },
            "gpu-training-budget": {
                "ml.p3.2xlarge": [
                    JumpStartBenchmarkStat({"name": "Latency", "value": "100", "unit": "Tokens/S"})
                ]
            },
        }


@pytest.mark.parametrize(
    "config_name, expected",
    [
        (
            None,
            {
                "Config Name": [
                    "neuron-inference",
                    "neuron-inference-budget",
                    "gpu-inference-budget",
                    "gpu-inference",
                ],
                "Instance Type": ["ml.p2.xlarge", "ml.p2.xlarge", "ml.p2.xlarge", "ml.p2.xlarge"],
                "Selected": ["No", "No", "No", "No"],
                "Instance Rate (USD/Hrs)": [
                    "0.0083000000",
                    "0.0083000000",
                    "0.0083000000",
                    "0.0083000000",
                ],
            },
        ),
        (
            "neuron-inference",
            {
                "Config Name": [
                    "neuron-inference",
                    "neuron-inference-budget",
                    "gpu-inference-budget",
                    "gpu-inference",
                ],
                "Instance Type": ["ml.p2.xlarge", "ml.p2.xlarge", "ml.p2.xlarge", "ml.p2.xlarge"],
                "Selected": ["Yes", "No", "No", "No"],
                "Instance Rate (USD/Hrs)": [
                    "0.0083000000",
                    "0.0083000000",
                    "0.0083000000",
                    "0.0083000000",
                ],
            },
        ),
    ],
)
def test_extract_metrics_from_deployment_configs(config_name, expected):
    data = utils.extract_metrics_from_deployment_configs(get_base_deployment_configs(), config_name)

    assert data == expected
