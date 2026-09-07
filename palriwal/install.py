# Copyright (c) 2026, Reformiqo and contributors
# For license information, please see license.txt

from palriwal.palriwal.tcs.custom_fields import setup_custom_fields


def after_install():
	setup_custom_fields()


def after_migrate():
	setup_custom_fields()
