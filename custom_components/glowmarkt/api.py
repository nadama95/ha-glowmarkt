"""API to collect data from."""

from datetime import datetime
from functools import lru_cache
from typing import Literal

import aiohttp

from .models import (
    Reading,
    ReadingData,
    Resource,
    ResourceOverview,
    ResourceTypeInfo,
    TariffData,
    TariffRates,
    VirtualEntity,
)


class GlowMarkt:
    """API for Glowmarkt."""

    BASE_URL = "https://api.glowmarkt.com/api/v0-1"
    APPLICATION_ID = "b0f1b774-a586-4f72-9edd-27ead8aa7a8d"

    def __init__(self, username: str, password: str):
        """Set up session with reuired headers."""
        self.session = aiohttp.ClientSession()
        self.session.headers.update(
            {"Content-Type": "application/json", "applicationId": self.APPLICATION_ID}
        )

        self.username = username
        self.password = password

    async def close(self) -> None:
        """Close Session."""
        await self.session.close()

    async def connect(self) -> None:
        """Connect to the API with provided credentials.

        Get JWT token required for further authentication.
        """
        response = await self.session.post(
            f"{self.BASE_URL}/auth",
            json={
                "username": self.username,
                "password": self.password,
            },
        )

        if response.status != 200:
            raise ValueError("Failed to authenticate")

        resp_json = await response.json()

        self.session.headers["token"] = resp_json["token"]

    @lru_cache
    async def get_virtual_entites(self) -> list[VirtualEntity]:
        """Get virtual entities."""
        response = await self.session.get(f"{self.BASE_URL}/virtualentity")

        if response.status != 200:
            raise ValueError("Failed to retrieve virtual entities")

        responseJson = await response.json()

        return [
            VirtualEntity(
                resources=[
                    ResourceOverview(
                        resource_id=r["resourceId"],
                        resource_type_id=r["resourceTypeId"],
                        name=r["name"],
                    )
                    for r in ve["resources"]
                ],
                name=ve["name"],
                id=ve["veId"],
            )
            for ve in responseJson
        ]

    async def get_resources(self, entity_id: str) -> list[Resource]:
        """Get virtual entity resources."""
        response = await self.session.get(
            f"{self.BASE_URL}/virtualentity/{entity_id}/resources"
        )

        if response.status != 200:
            raise ValueError("Failed to retrieve virtual entities")

        responseJson = await response.json()

        return [
            Resource(
                active=r["active"],
                resource_type_id=r["resourceTypeId"],
                owner_id=r["ownerId"],
                name=r["name"],
                description=r["description"],
                label=r["label"],
                data_source_resource_type_info=ResourceTypeInfo(
                    unit=r["dataSourceResourceTypeInfo"]["unit"],
                    type=r["dataSourceResourceTypeInfo"]["type"],
                ),
                data_source_type=r["dataSourceType"],
                classifier=r["classifier"],
                base_unit=r["baseUnit"],
                resource_id=r["resourceId"],
                updated_at=r["updatedAt"],
                created_at=r["createdAt"],
                data_souce_unit_info=r["dataSourceUnitInfo"],
            )
            for r in responseJson["resources"]
        ]

    async def catchup(self, resource_id: str) -> None:
        """Tell API to pull latest DCC data."""
        await self.session.get(f"{self.BASE_URL}/resource/{resource_id}/catchup")

    async def get_reading(
        self,
        resource_id: str,
        from_time: datetime,
        to_time: datetime,
        period: Literal["PT30M30", "PT1H", "P1D", "P1W", "P1M", "P1Y"] = "PT1H",
    ) -> Reading:
        """Get readings for a specific resource."""
        from_str = from_time.strftime("%Y-%m-%dT%H:%M:%S")
        to_str = to_time.strftime("%Y-%m-%dT%H:%M:%S")

        url = f"{self.BASE_URL}/resource/{resource_id}/readings?from={from_str}&to={to_str}&period={period}&function=sum"
        response = await self.session.get(url)

        if response.status != 200:
            raise ValueError("Failed to retrieve readings")

        data = (await response.json())["data"]

        result: list[ReadingData] = []

        for epoch, value in data:
            timestamp = datetime.fromtimestamp(epoch)
            result.append(ReadingData(datestamp=timestamp, value=value))

        return Reading(data=result)

    async def get_tariff(self, resource_id: str):
        """Get tariff from specific resource."""
        url = f"{self.BASE_URL}/resource/{resource_id}/tariff"
        response = await self.session.get(url)

        if response.status != 200:
            raise ValueError("Failed to retrieve tariff")

        data = (await response.json())["data"][0]

        return TariffData(
            current_rates=TariffRates(
                rate=data["currentRates"]["rate"],
                standing_charge=data["currentRates"]["standingCharge"],
            )
        )
