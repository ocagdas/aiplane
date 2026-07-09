from __future__ import annotations

import json
import os
import subprocess
import shutil
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from io import BytesIO, StringIO
from pathlib import Path
import unittest
from unittest.mock import patch

import aiplane.cli as cli_module
import aiplane.mcp as mcp_module
from aiplane import config as agent_config
from aiplane.approvals import ApprovalHandler
from aiplane.audit import AuditLogger
from aiplane.benchmarks import BenchmarkRunner
from aiplane.backends import BackendResult, OllamaBackend
from aiplane.cli import main as cli_main
from aiplane.code_tasks import CodeTaskResult, CodeTaskRunner
from aiplane.config import (
    create_profile,
    default_profile,
    init_local_config,
    list_config_templates,
    list_profile_templates,
    load_local_config,
    parse_yaml,
    remove_profile,
    repair_profile,
    resolve_profile_name,
    set_default_profile,
)
from aiplane.deploy import DeployManager
from aiplane.env import EnvironmentManager
from aiplane.hardware import HardwareManager
from aiplane.integrations import IntegrationManager
from aiplane.machines import MachineManager
from aiplane.mcp import AiplaneMcpServer, _read_message, _write_message, mcp_manifest
from aiplane.model_catalog import ModelCatalog, _discovered_model_entry
from aiplane.model_filters import (
    ACCELERATOR_API_CHOICES,
    GPU_VENDOR_CHOICES,
    MODEL_FILTER_SCHEMA_PROPERTIES,
    MODEL_SORT_CHOICES,
)
from aiplane.model_output import group_model_rows
from aiplane.models import Profile
from aiplane.orchestrators import OrchestratorCatalog
from aiplane.policy import PolicyEngine
from aiplane.providers import ProviderModelsResult, ProviderRegistry
from aiplane.remote import RemoteManager
from aiplane.router import Router
from aiplane.runtime_catalog import RuntimeCatalog
from aiplane.runtime_pull import ollama_model_id, runtime_pull_support
from aiplane.secrets import contains_secret, redact
from aiplane.stacks import StackManager
from aiplane.tools import ToolExecutor

from .http_fixtures import OpenAICompatibleTestHandler, TestHttpServer
from .profile_fixtures import (
    _REAL_LOAD_PROFILE,
    _ensure_repo_test_profile,
    _isolated_profiles_dir,
    _isolated_test_profile,
    _load_profile_with_test_models,
    _test_model_fixture,
    load_profile,
)

__all__ = [
    "ACCELERATOR_API_CHOICES",
    "AiplaneMcpServer",
    "ApprovalHandler",
    "AuditLogger",
    "BackendResult",
    "BenchmarkRunner",
    "BytesIO",
    "CodeTaskResult",
    "CodeTaskRunner",
    "DeployManager",
    "EnvironmentManager",
    "GPU_VENDOR_CHOICES",
    "HardwareManager",
    "IntegrationManager",
    "MODEL_FILTER_SCHEMA_PROPERTIES",
    "MODEL_SORT_CHOICES",
    "MachineManager",
    "ModelCatalog",
    "OllamaBackend",
    "OpenAICompatibleTestHandler",
    "OrchestratorCatalog",
    "Path",
    "PolicyEngine",
    "Profile",
    "ProviderModelsResult",
    "ProviderRegistry",
    "RemoteManager",
    "Router",
    "RuntimeCatalog",
    "StackManager",
    "StringIO",
    "TestHttpServer",
    "ToolExecutor",
    "_REAL_LOAD_PROFILE",
    "_discovered_model_entry",
    "_ensure_repo_test_profile",
    "_isolated_profiles_dir",
    "_isolated_test_profile",
    "_load_profile_with_test_models",
    "_read_message",
    "_test_model_fixture",
    "_write_message",
    "agent_config",
    "cli_main",
    "cli_module",
    "contains_secret",
    "create_profile",
    "default_profile",
    "group_model_rows",
    "init_local_config",
    "json",
    "list_config_templates",
    "list_profile_templates",
    "load_local_config",
    "load_profile",
    "mcp_manifest",
    "mcp_module",
    "ollama_model_id",
    "os",
    "parse_yaml",
    "patch",
    "redact",
    "redirect_stderr",
    "redirect_stdout",
    "remove_profile",
    "repair_profile",
    "resolve_profile_name",
    "runtime_pull_support",
    "set_default_profile",
    "shutil",
    "subprocess",
    "sys",
    "tempfile",
    "unittest",
]
