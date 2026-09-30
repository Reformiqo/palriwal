# Copyright (c) 2026, Reformiqo and contributors
# For license information, please see license.txt

from palriwal.palriwal.delivery_order.custom_fields import (
	setup_custom_fields as setup_delivery_order_fields,
)
from palriwal.palriwal.tcs.custom_fields import setup_custom_fields


def after_install():
	setup_custom_fields()
	setup_delivery_order_fields()


def after_migrate():
	setup_custom_fields()
	setup_delivery_order_fields()
