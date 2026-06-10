#!/usr/bin/env python3
"""CDK app entry point."""

import aws_cdk as cdk
from stack import YtDigestStack

app = cdk.App()
YtDigestStack(app, "YtDigestStack")
app.synth()
