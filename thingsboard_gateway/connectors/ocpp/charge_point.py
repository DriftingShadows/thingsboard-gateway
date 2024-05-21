#     Copyright 2024. ThingsBoard
#
#     Licensed under the Apache License, Version 2.0 (the "License");
#     you may not use this file except in compliance with the License.
#     You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.

import simplejson
from ocpp.v16 import ChargePoint as CP
from ocpp.routing import on
from ocpp.v16.enums import Action, RegistrationStatus, DataTransferStatus, AuthorizationStatus
from ocpp.v16 import call_result, datatypes
from datetime import datetime

from thingsboard_gateway.tb_utility.tb_loader import TBModuleLoader

import random

class ChargePoint(CP):
    def __init__(self, charge_point_id, websocket, config, callback, logger):
        super(ChargePoint, self).__init__(charge_point_id, websocket)
        self._log = logger
        self._config = config
        self._callback = callback
        self._uplink_converter = self._load_converter(config['uplink_converter_name'])(self._config, self._log)
        self._profile = {}
        self.name = charge_point_id
        self.type = "Charge Point"
        self._authorized = False
        self._stopped = False

    @property
    def config(self):
        return self._config

    @property
    def authorized(self):
        return self._authorized

    @authorized.setter
    def authorized(self, is_auth: bool):
        self._authorized = is_auth

    async def start(self):
        while not self._stopped:
            message = await self._connection.recv()

            await self.route_message(message)

    @staticmethod
    def _load_converter(converter_name):
        return TBModuleLoader.import_module('ocpp', converter_name)

    async def close(self):
        self._stopped = True
        return await self._connection.close()

    @on(Action.BootNotification)
    def on_boot_notification(self, charge_point_vendor: str, charge_point_model: str, **kwargs):
        self._profile = {
            'charge_point_id': self.id,
            'Vendor': charge_point_vendor,
            'Model': charge_point_model
        }
        self.name = self._uplink_converter.get_device_name(self._profile)
        self.type = self._uplink_converter.get_device_type(self._profile)

        self._callback((self._uplink_converter,
                        {'deviceName': self.id, 'deviceType': self.type, 'messageType': Action.BootNotification,
                         'profile': self._profile},
                        {'vendor': charge_point_vendor, 'model': charge_point_model}))

        return call_result.BootNotificationPayload(
            current_time=datetime.utcnow().isoformat(),
            interval=30,
            status=RegistrationStatus.accepted
        )

    @on(Action.Authorize)
    def on_authorize(self, id_tag: str, **kwargs):
        self._log.debug('In Authorize')
        if self.authorized:
            return call_result.AuthorizePayload(id_tag_info={'status': 'Accepted'})

        return call_result.AuthorizePayload(id_tag_info={'status': 'Not authorized'})

    @on(Action.Heartbeat)
    def on_heartbeat(self):
        current_time = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S') + "Z"

        self._callback((self._uplink_converter,
                {'deviceName': self.id, 'deviceType': self.type, 'messageType': Action.Heartbeat,
                    'profile': self._profile}, {"last_heartbeat": current_time}))

        return call_result.HeartbeatPayload(
            current_time=current_time
        )

    @on(Action.MeterValues)
    def on_meter_values(self, **kwargs):
        self._log.debug('In MeterValues')
        # try:
        #     if(kwargs['meter_value'][0]['sampled_value'][1]['measurand'] == 'Current.Import'):
        #         current = kwargs['meter_value'][0]['sampled_value'][1]['value']
        #         kwargs['current'] = current
        # except Exception as e:
        #     self._log.debug(e)
            
        self._callback((self._uplink_converter,
                        {'deviceName': self.name, 'deviceType': self.type, 'messageType': Action.MeterValues,
                         'profile': self._profile}, kwargs))
        return call_result.MeterValuesPayload()

    @on(Action.DataTransfer)
    def on_data_transfer(self, **kwargs):
        for (key, value) in kwargs.items():
            try:
                kwargs[key] = simplejson.loads(value)
            except (TypeError, ValueError):
                continue

        self._callback((self._uplink_converter,
                        {'deviceName': self.name, 'deviceType': self.type, 'messageType': Action.DataTransfer,
                         'profile': self._profile}, kwargs))
        return call_result.DataTransferPayload(status=DataTransferStatus.accepted)

    @on(Action.StartTransaction)
    def on_start_transaction(self, connector_id: int, id_tag: str, meter_start: int, timestamp,  **kwargs):
        self._log.debug('In Start Transaction')
        id_tag_info = datatypes.IdTagInfo(status=AuthorizationStatus.accepted)
        transaction_id = random.randint(1, 1000)
        self._callback((self._uplink_converter,
                {'deviceName': self.name, 'deviceType': self.type, 'messageType': Action.StartTransaction,
                    'profile': self._profile}, {"current": 0, "sampled_value": meter_start, "meter_start": meter_start, "start_timestamp": timestamp, "ongoing_transaction": True, "transaction_id": transaction_id, "transaction_info": {"type": "start", "payload": {"timestamp": timestamp, "meter": meter_start, "txn_id": transaction_id}}}))

        return call_result.StartTransactionPayload(transaction_id=transaction_id, id_tag_info=id_tag_info)

    @on(Action.StopTransaction)
    def on_stop_transaction(self, meter_stop: int, timestamp, transaction_id: str, **kwargs):
        self._log.debug('In stop transaction')
        self._callback((self._uplink_converter,
        {'deviceName': self.name, 'deviceType': self.type, 'messageType': Action.StopTransaction,
            'profile': self._profile}, {"meter_stop": meter_stop, "stop_timestamp": timestamp, "ongoing_transaction": False, "sampled_value": 0, "current": 0, "transaction_id": transaction_id, "transaction_info": {"type": "stop", "payload": {"timestamp": timestamp, "meter": meter_stop, "txn_id": transaction_id}} }))

        return call_result.StopTransactionPayload()

    @on(Action.StatusNotification)
    def on_status_notification(self, connector_id: int, error_code, **kwargs):
        self._callback((self._uplink_converter,
        {'deviceName': self.id, 'deviceType': self.type, 'messageType': Action.StatusNotification,
        'profile': self._profile}, kwargs))

        return call_result.StatusNotificationPayload()