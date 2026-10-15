"""Generate additional domain-specific AUTOSAR HLD sample PDFs.

Produces five extra PDFs (ADAS, powertrain, body control, network gateway,
diagnostics) with the same layout conventions as generate_sample.py so the
ingestion pipeline, entity extraction, checks and RAG demo can run on more
than the two Vehicle Motion Control revisions.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

PAGE_W, PAGE_H = 595, 842
MARGIN = 50
BODY_SIZE = 10.0


class Builder:
    def __init__(self) -> None:
        self.doc = pymupdf.open()
        self.page: pymupdf.Page | None = None
        self.y = MARGIN
        self.title = "HLD"
        self._new_page()

    def _new_page(self) -> None:
        self.page = self.doc.new_page(width=PAGE_W, height=PAGE_H)
        self.y = MARGIN

    def _ensure(self, height: float) -> None:
        if self.y + height > PAGE_H - MARGIN:
            self._new_page()

    def heading(self, text: str, level: int = 1) -> None:
        size = {1: 15.0, 2: 12.5, 3: 11.0}.get(level, 11.0)
        self._ensure(size + 18)
        self.y += 8 if level > 1 else 4
        assert self.page is not None
        self.page.insert_text((MARGIN, self.y + size), text, fontsize=size, fontname="hebo")
        self.y += size + 8

    def para(self, text: str) -> None:
        assert self.page is not None
        rect = pymupdf.Rect(MARGIN, self.y, PAGE_W - MARGIN, PAGE_H - MARGIN)
        remaining = self.page.insert_textbox(rect, text, fontsize=BODY_SIZE, fontname="helv", align=0)
        if remaining < 0:
            self._new_page()
            assert self.page is not None
            rect = pymupdf.Rect(MARGIN, self.y, PAGE_W - MARGIN, PAGE_H - MARGIN)
            remaining = self.page.insert_textbox(rect, text, fontsize=BODY_SIZE, fontname="helv", align=0)
        self.y = PAGE_H - MARGIN - remaining + 6

    def gap(self, amount: float = 8) -> None:
        self.y += amount

    def page_break(self) -> None:
        self._new_page()

    def table(self, headers: list[str], rows: list[list[str]], widths: list[float]) -> None:
        assert self.page is not None
        row_h = 15.0
        total_h = row_h * (len(rows) + 1)
        if self.y + total_h > PAGE_H - MARGIN:
            self._new_page()
        x_positions = [MARGIN]
        for width in widths:
            x_positions.append(x_positions[-1] + width)

        all_rows = [headers] + rows
        for row_index, row in enumerate(all_rows):
            top = self.y + row_index * row_h
            bottom = top + row_h
            for col_index, cell in enumerate(row):
                left, right = x_positions[col_index], x_positions[col_index + 1]
                font = "hebo" if row_index == 0 else "helv"
                max_chars = max(4, int((right - left - 6) / (BODY_SIZE * 0.5)))
                self.page.insert_text((left + 3, bottom - 4.5), str(cell)[:max_chars], fontsize=8.2, fontname=font)
            self.page.draw_line((x_positions[0], bottom), (x_positions[-1], bottom))
        for x in x_positions:
            self.page.draw_line((x, self.y), (x, self.y + total_h))
        self.page.draw_rect(pymupdf.Rect(x_positions[0], self.y, x_positions[-1], self.y + total_h), width=0.6)
        self.y += total_h + 10

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.doc.set_metadata(
            {
                "title": self.title,
                "author": "Reference Solution Document",
                "subject": "AUTOSAR High-Level Design",
                "keywords": "AUTOSAR,HLD,architecture",
            }
        )
        self.doc.save(path)
        self.doc.close()


@dataclass
class DomainSpec:
    system_name: str
    doc_id: str
    revision: str
    title: str
    summary: str
    scope: str
    context: str
    components: list[list[str]] = field(default_factory=list)
    ports: list[list[str]] = field(default_factory=list)
    signals: list[list[str]] = field(default_factory=list)
    flows: list[tuple[str, str]] = field(default_factory=list)
    timing: str = ""
    bsw: list[str] = field(default_factory=list)
    diagnostics: str = ""
    limitations: str = "TBD."


SPECS: list[DomainSpec] = [
    DomainSpec(
        system_name="Advanced Driver Assistance System",
        doc_id="ADAS-HLD-0012",
        revision="C",
        title="ADAS Domain High-Level Design (HLD)",
        summary=(
            "This document describes the software architecture of the advanced driver "
            "assistance domain: camera processing, radar fusion, lane assistance and "
            "adaptive cruise control components, ports, interfaces, signals and flows."
        ),
        scope=(
            "The ADAS domain covers camera object detection, mid-range radar fusion, "
            "lane keeping assist and adaptive cruise control. Out of scope: raw sensor "
            "calibration, hardware wiring and production software details."
        ),
        context=(
            "The domain runs on AdasEcu with a dedicated vision accelerator. Gateway "
            "exchange with the vehicle motion domain is performed by AdasGateway over "
            "the chassis Ethernet link."
        ),
        components=[
            ["CameraProcessingUnit", "ApplicationSwComponentType", "Camera object detection and classification"],
            ["RadarFusionEngine", "ApplicationSwComponentType", "Mid-range radar target fusion"],
            ["LaneAssistController", "ApplicationSwComponentType", "Lane keeping assist arbitration"],
            ["AdaptiveCruiseController", "ApplicationSwComponentType", "Adaptive cruise control logic"],
            ["ObstacleDetector", "ApplicationSwComponentType", "Static and dynamic obstacle tracking"],
            ["AdasSignalService", "ServiceSwComponentType", "ADAS signal gateway service"],
            ["AdasGateway", "EcuAbstractionSwComponentType", "Cross-domain gateway exchange"],
            ["AdasFrontendComposition", "CompositionSwComponentType", "Composition of the ADAS components"],
        ],
        ports=[
            ["CameraObjectsOut", "provided", "ObjectListI", "CameraProcessingUnit"],
            ["RadarObjectsIn", "required", "RadarObjectListI", "RadarFusionEngine"],
            ["LaneOffsetOut", "provided", "LaneOffsetI", "LaneAssistController"],
            ["AccTargetOut", "provided", "AccTargetI", "AdaptiveCruiseController"],
            ["ObstacleListOut", "provided", "ObstacleListI", "ObstacleDetector"],
            ["AdasGatewayIn", "required", "AdasSignalSetI", "AdasSignalService"],
            ["GatewayToMotion", "provided", "MotionCommandI", "AdasGateway"],
            ["SteeringCommandOut", "provided", "SteeringCommandI", "LaneAssistController"],
        ],
        signals=[
            ["CameraObjectList", "ObjectListI", "CameraProcessingUnit", "RadarFusionEngine", "64"],
            ["RadarObjectList", "RadarObjectListI", "RadarFusionEngine", "ObstacleDetector", "48"],
            ["LaneOffset", "LaneOffsetI", "LaneAssistController", "AdasGateway", "12"],
            ["AccTargetDistance", "AccTargetI", "AdaptiveCruiseController", "GatewayToMotion", "16"],
            ["ObstacleClass", "ObstacleListI", "ObstacleDetector", "CameraProcessingUnit", "8"],
            ["SteeringCommand", "SteeringCommandI", "LaneAssistController", "GatewayToMotion", "16"],
            ["AdasMode", "AdasModeI", "AdaptiveCruiseController", "LaneAssistController", "4"],
        ],
        flows=[
            (
                "Camera object flow",
                "CameraProcessingUnit detects objects and publishes CameraObjectsOut over "
                "ObjectListI. RadarFusionEngine consumes CameraObjectsOut together with "
                "RadarObjectsIn and produces a fused ObstacleListI consumed by "
                "ObstacleDetector for downstream arbitration.",
            ),
            (
                "Lane keeping flow",
                "LaneAssistController computes LaneOffset from camera lane markers and "
                "requests a steering correction through SteeringCommandI. "
                "AdaptiveCruiseController consumes AdasMode to suppress lane requests "
                "during manual override.",
            ),
            (
                "Adaptive cruise flow",
                "AdaptiveCruiseController tracks AccTargetDistance from the fused radar "
                "list and requests torque modulation from PowertrainGateway through "
                "MotionCommandI via AdasGateway.",
            ),
        ],
        timing=(
            "TimingEvent CameraFrameEvent triggers ProcessCameraFrameRunnable every "
            "40 ms. TimingEvent RadarSweepEvent triggers FuseRadarTargetsRunnable every "
            "20 ms. TimingEvent LaneUpdateEvent triggers UpdateLaneAssistRunnable every "
            "25 ms. All runnables are scheduled by AdasTask on AdasEcu."
        ),
        bsw=[
            "Signal routing uses Com and PduR. Incoming Ethernet frames are handled by "
            "SoAd and TcpIp. NvM stores the camera calibration block. Rte provides the "
            "port API used by all ADAS application components.",
            "Mode management is performed by BswM and EcuM. Watchdog supervision for "
            "AdasTask is performed by WdgM. The vision accelerator interface uses Xcp "
            "for online calibration exchange.",
            "The diagnostic path routes UDS requests through Dcm and Dem. "
            "AdasSignalService consumes AdasSignalSetI and forwards fault reports to "
            "the tester over DoIP.",
        ],
        diagnostics=(
            "DTCs for camera blockage, radar misalignment and fusion timeout are "
            "defined in the diagnostics specification. The HLD only defines the "
            "reporting path: component to Dcm to SoAd."
        ),
        limitations=(
            "CameraProcessingUnit degrades gracefully under heavy rain, but full "
            "performance recovery after blockage is not specified in this revision."
        ),
    ),
    DomainSpec(
        system_name="Powertrain Control System",
        doc_id="PT-HLD-0007",
        revision="D",
        title="Powertrain Control High-Level Design (HLD)",
        summary=(
            "This document describes the software architecture of the powertrain "
            "control domain: engine management, transmission control, torque "
            "coordination and emissions aftertreatment components and interfaces."
        ),
        scope=(
            "The powertrain domain covers engine torque production, gear ratio "
            "management, torque limitation and aftertreatment monitoring. Out of "
            "scope: combustion calibration maps, hardware sensor pin mapping and "
            "production software implementation details."
        ),
        context=(
            "The domain runs on PowertrainEcu. Torque requests from the vehicle "
            "motion and ADAS domains arrive via PowertrainGateway over the chassis "
            "CAN bus at 500 kbit/s."
        ),
        components=[
            ["EngineManagementUnit", "ApplicationSwComponentType", "Engine torque and fuelling control"],
            ["TransmissionController", "ApplicationSwComponentType", "Gear ratio and shift control"],
            ["TorqueCoordinator", "ApplicationSwComponentType", "Cross-domain torque arbitration"],
            ["AftertreatmentMonitor", "ApplicationSwComponentType", "Emissions aftertreatment supervision"],
            ["StartStopManager", "ApplicationSwComponentType", "Start-stop strategy and restart logic"],
            ["PowertrainSignalService", "ServiceSwComponentType", "Powertrain signal gateway service"],
            ["PowertrainGateway", "EcuAbstractionSwComponentType", "Cross-domain gateway exchange"],
            ["PowertrainMainComposition", "CompositionSwComponentType", "Composition of the domain components"],
        ],
        ports=[
            ["TorqueRequestIn", "required", "TorqueRequestI", "TorqueCoordinator"],
            ["EngineTorqueOut", "provided", "EngineTorqueI", "EngineManagementUnit"],
            ["GearRatioOut", "provided", "GearRatioI", "TransmissionController"],
            ["AftertreatmentStatusOut", "provided", "AftertreatmentStatusI", "AftertreatmentMonitor"],
            ["StartStopStateOut", "provided", "StartStopStateI", "StartStopManager"],
            ["PowertrainGatewayIn", "required", "PowertrainSignalSetI", "PowertrainSignalService"],
            ["GatewayToMotion", "provided", "VehicleSpeedI", "PowertrainGateway"],
            ["GatewayToAdas", "provided", "MotionCommandI", "PowertrainGateway"],
        ],
        signals=[
            ["RequestedTorque", "TorqueRequestI", "TorqueCoordinator", "EngineManagementUnit", "12"],
            ["ActualEngineTorque", "EngineTorqueI", "EngineManagementUnit", "TorqueCoordinator", "12"],
            ["CurrentGearRatio", "GearRatioI", "TransmissionController", "TorqueCoordinator", "8"],
            ["CatalystTemperature", "AftertreatmentStatusI", "AftertreatmentMonitor", "EngineManagementUnit", "12"],
            ["StartStopActive", "StartStopStateI", "StartStopManager", "TransmissionController", "1"],
            ["EngineSpeed", "EngineSpeedI", "EngineManagementUnit", "TransmissionController", "16"],
            ["TransmissionMode", "TransmissionModeI", "TransmissionController", "StartStopManager", "4"],
        ],
        flows=[
            (
                "Torque arbitration flow",
                "TorqueCoordinator consumes TorqueRequestIn from the vehicle motion "
                "domain and MotionCommandI from the ADAS domain, applies priority "
                "limits and publishes RequestedTorque to EngineManagementUnit. "
                "EngineManagementUnit confirms through ActualEngineTorque.",
            ),
            (
                "Shift intervention flow",
                "TransmissionController consumes EngineSpeed and CurrentGearRatio to "
                "request temporary torque reduction from TorqueCoordinator during "
                "shift events. StartStopManager suspends start-stop during active "
                "shifts.",
            ),
            (
                "Aftertreatment flow",
                "AftertreatmentMonitor tracks CatalystTemperature and raises a "
                "limp-home request to EngineManagementUnit when thresholds are "
                "exceeded. DiagnosticsFrontend reads the fault state over "
                "DiagnosticServiceI.",
            ),
        ],
        timing=(
            "TimingEvent TorqueArbitrationEvent triggers CoordinateTorqueRunnable every "
            "10 ms. TimingEvent ShiftMonitorEvent triggers MonitorShiftRunnable every "
            "20 ms. TimingEvent AftertreatmentSampleEvent triggers "
            "SampleAftertreatmentRunnable every 100 ms. All runnables are scheduled by "
            "PowertrainTask on PowertrainEcu."
        ),
        bsw=[
            "Signal routing uses Com and PduR. Incoming frames are handled by CanIf on "
            "PowertrainEcu. NvM stores the shift strategy calibration block. Rte "
            "provides the port API used by all powertrain application components.",
            "Mode management is performed by BswM and EcuM. Watchdog supervision for "
            "PowertrainTask is performed by WdgM. The gateway maps IPdu to NPdu inside "
            "PowertrainGateway before transmission.",
            "The diagnostic path routes UDS requests through Dcm and Dem. "
            "PowertrainSignalService consumes PowertrainSignalSetI and forwards "
            "routine results to the tester.",
        ],
        diagnostics=(
            "DTCs for catalyst overtemperature, shift timeout and torque deviation are "
            "defined in the diagnostics specification. The HLD only defines the "
            "reporting path: component to Dcm to CanIf."
        ),
        limitations=(
            "TorqueCoordinator priority arbitration between ADAS and motion requests "
            "is fixed at compile time in this revision."
        ),
    ),
    DomainSpec(
        system_name="Body Control System",
        doc_id="BC-HLD-0021",
        revision="B",
        title="Body Control High-Level Design (HLD)",
        summary=(
            "This document describes the software architecture of the body control "
            "domain: exterior lighting, climate control, seat comfort and access "
            "management components, ports, interfaces, signals and functional flows."
        ),
        scope=(
            "The body control domain covers exterior lighting commands, cabin "
            "climate regulation, seat comfort actuators and keyless access state "
            "management. Out of scope: actuator driver electronics and production "
            "wiring harness details."
        ),
        context=(
            "The domain runs on BodyEcu and communicates with the vehicle motion "
            "domain for lamp commands and speed signals through BodyGateway over "
            "the body CAN bus at 125 kbit/s."
        ),
        components=[
            ["ExteriorLightingController", "ApplicationSwComponentType", "Headlamp and indicator logic"],
            ["ClimateControlUnit", "ApplicationSwComponentType", "Cabin temperature regulation"],
            ["SeatComfortManager", "ApplicationSwComponentType", "Seat adjustment and comfort features"],
            ["AccessManagementUnit", "ApplicationSwComponentType", "Keyless access and authorization"],
            ["WiperController", "ApplicationSwComponentType", "Wiper and washer automation"],
            ["BodySignalService", "ServiceSwComponentType", "Body signal gateway service"],
            ["BodyGateway", "EcuAbstractionSwComponentType", "Cross-domain gateway exchange"],
            ["BodyControlComposition", "CompositionSwComponentType", "Composition of the body components"],
        ],
        ports=[
            ["LampCommandIn", "required", "LampCommandI", "ExteriorLightingController"],
            ["IndicatorStateOut", "provided", "IndicatorStateI", "ExteriorLightingController"],
            ["CabinTemperatureOut", "provided", "CabinTemperatureI", "ClimateControlUnit"],
            ["SeatPositionOut", "provided", "SeatPositionI", "SeatComfortManager"],
            ["AccessStateOut", "provided", "AccessStateI", "AccessManagementUnit"],
            ["BodyGatewayIn", "required", "BodySignalSetI", "BodySignalService"],
            ["GatewayToMotion", "provided", "LampCommandI", "BodyGateway"],
            ["WiperStateOut", "provided", "WiperStateI", "WiperController"],
        ],
        signals=[
            ["LampCommand", "LampCommandI", "BodyGateway", "ExteriorLightingController", "8"],
            ["IndicatorBlink", "IndicatorStateI", "ExteriorLightingController", "WiperController", "1"],
            ["CabinTemperature", "CabinTemperatureI", "ClimateControlUnit", "BodySignalService", "8"],
            ["SeatMemoryIndex", "SeatPositionI", "SeatComfortManager", "AccessManagementUnit", "4"],
            ["AccessGranted", "AccessStateI", "AccessManagementUnit", "ClimateControlUnit", "1"],
            ["RainSensorValue", "RainSensorI", "WiperController", "ExteriorLightingController", "8"],
            ["AmbientLightLevel", "AmbientLightI", "BodyGateway", "ExteriorLightingController", "8"],
        ],
        flows=[
            (
                "Exterior lighting flow",
                "BodyGateway forwards LampCommand from the vehicle motion domain to "
                "ExteriorLightingController. ExteriorLightingController consumes "
                "AmbientLightLevel and RainSensorValue to decide headlamp state and "
                "publishes IndicatorStateOut.",
            ),
            (
                "Access and comfort flow",
                "AccessManagementUnit authorizes the driver key and publishes "
                "AccessStateOut. ClimateControlUnit consumes AccessGranted to begin "
                "pre-conditioning. SeatComfortManager applies the stored "
                "SeatMemoryIndex for the authorized driver.",
            ),
            (
                "Wiper automation flow",
                "WiperController consumes RainSensorValue and publishes WiperStateOut. "
                "WiperController requests reduced wiper activity during vehicle "
                "standstill while StartStopStateI is active.",
            ),
        ],
        timing=(
            "TimingEvent LightingUpdateEvent triggers UpdateLightingRunnable every "
            "50 ms. TimingEvent ClimateControlEvent triggers RegulateClimateRunnable "
            "every 200 ms. TimingEvent AccessPollEvent triggers PollAccessStateRunnable "
            "every 100 ms. All runnables are scheduled by BodyTask on BodyEcu."
        ),
        bsw=[
            "Signal routing uses Com and PduR. Incoming frames are handled by CanIf on "
            "BodyEcu. NvM stores the seat memory and lighting preference blocks. Rte "
            "provides the port API used by all body application components.",
            "Mode management is performed by BswM and EcuM. Watchdog supervision for "
            "BodyTask is performed by WdgM. The wiper motor interface uses IoHwAb for "
            "pulse width modulation control.",
            "The diagnostic path routes UDS requests through Dcm and Dem. "
            "BodySignalService consumes BodySignalSetI and forwards routine results "
            "to the tester.",
        ],
        diagnostics=(
            "DTCs for lamp circuit failure, climate sensor plausibility and access "
            "antenna fault are defined in the diagnostics specification. The HLD only "
            "defines the reporting path: component to Dcm to CanIf."
        ),
        limitations=(
            "SeatComfortManager supports two memory positions per seat in this "
            "revision; more positions require a NvM layout change."
        ),
    ),
    DomainSpec(
        system_name="Network Gateway System",
        doc_id="GW-HLD-0003",
        revision="A",
        title="Central Gateway High-Level Design (HLD)",
        summary=(
            "This document describes the software architecture of the central "
            "network gateway: CAN routing, Ethernet backbone bridging, diagnostic "
            "multiplexing and time synchronization components and interfaces."
        ),
        scope=(
            "The central gateway covers inter-bus routing between chassis CAN, body "
            "CAN, powertrain CAN and the Ethernet backbone, plus diagnostic "
            "multiplexing. Out of scope: physical transceiver design and production "
            "connector pin assignment."
        ),
        context=(
            "The gateway runs on GatewayEcu and interconnects ChassisEcu, "
            "PowertrainEcu, BodyEcu and the ADAS domain over a switched Ethernet "
            "backbone."
        ),
        components=[
            ["CanRoutingTableManager", "ApplicationSwComponentType", "CAN frame routing tables"],
            ["EthernetBridgeController", "ApplicationSwComponentType", "Ethernet backbone bridging"],
            ["DiagnosticMultiplexer", "ApplicationSwComponentType", "UDS diagnostic routing"],
            ["TimeSyncCoordinator", "ApplicationSwComponentType", "Global time synchronization"],
            ["SecurityGateway", "ApplicationSwComponentType", "Secure onboard communication"],
            ["GatewaySignalService", "ServiceSwComponentType", "Gateway signal service"],
            ["CentralGatewayAbstraction", "EcuAbstractionSwComponentType", "Gateway hardware abstraction"],
            ["NetworkTopologyComposition", "CompositionSwComponentType", "Composition of gateway components"],
        ],
        ports=[
            ["CanRoutingIn", "required", "CanFrameI", "CanRoutingTableManager"],
            ["EthernetBridgeOut", "provided", "EthernetFrameI", "EthernetBridgeController"],
            ["DiagRouteOut", "provided", "DiagRoutingI", "DiagnosticMultiplexer"],
            ["TimeSyncOut", "provided", "GlobalTimeI", "TimeSyncCoordinator"],
            ["SecuredFrameOut", "provided", "SecuredFrameI", "SecurityGateway"],
            ["GatewayServiceIn", "required", "GatewayServiceI", "GatewaySignalService"],
            ["TopologyQueryOut", "provided", "TopologyQueryI", "CentralGatewayAbstraction"],
            ["StatusReportOut", "provided", "GatewayStatusI", "SecurityGateway"],
        ],
        signals=[
            ["ChassisCanFrame", "CanFrameI", "CanRoutingTableManager", "EthernetBridgeController", "64"],
            ["BackboneFrame", "EthernetFrameI", "EthernetBridgeController", "DiagnosticMultiplexer", "128"],
            ["UdsResponse", "DiagRoutingI", "DiagnosticMultiplexer", "CanRoutingTableManager", "32"],
            ["GlobalTimeValue", "GlobalTimeI", "TimeSyncCoordinator", "SecurityGateway", "32"],
            ["SecuredPayload", "SecuredFrameI", "SecurityGateway", "EthernetBridgeController", "96"],
            ["GatewayMode", "GatewayModeI", "GatewaySignalService", "CanRoutingTableManager", "4"],
            ["TopologyVersion", "TopologyQueryI", "CentralGatewayAbstraction", "GatewaySignalService", "8"],
        ],
        flows=[
            (
                "Chassis to backbone routing flow",
                "CanRoutingTableManager receives ChassisCanFrame from the chassis CAN "
                "bus and forwards converted frames to EthernetBridgeController for "
                "backbone transmission. SecurityGateway signs the payload before "
                "transmission through SecuredFrameI.",
            ),
            (
                "Diagnostic multiplexing flow",
                "DiagnosticMultiplexer routes UDS requests from the Ethernet backbone "
                "to the addressed ECU over the corresponding CAN bus and returns "
                "UdsResponse to the tester. CanRoutingTableManager forwards the "
                "response frames.",
            ),
            (
                "Time synchronization flow",
                "TimeSyncCoordinator broadcasts GlobalTimeValue to all connected ECUs. "
                "SecurityGateway rejects frames with stale timestamps to protect "
                "against replay attacks.",
            ),
        ],
        timing=(
            "TimingEvent RoutingFlushEvent triggers FlushRoutingTablesRunnable every "
            "10 ms. TimingEvent TimeSyncEvent triggers BroadcastGlobalTimeRunnable "
            "every 100 ms. TimingEvent SecurityCheckEvent triggers "
            "VerifyFrameSecurityRunnable every 10 ms. All runnables are scheduled by "
            "GatewayTask on GatewayEcu."
        ),
        bsw=[
            "Signal routing uses Com and PduR across all CAN buses. Incoming Ethernet "
            "frames are handled by SoAd and TcpIp. NvM stores the routing tables and "
            "security keys. Rte provides the port API used by all gateway components.",
            "Mode management is performed by BswM and EcuM. Watchdog supervision for "
            "GatewayTask is performed by WdgM. The Ethernet switch configuration is "
            "applied through Spi during startup.",
            "The diagnostic path routes UDS requests through Dcm and Dem. "
            "GatewaySignalService consumes GatewayServiceI and forwards topology "
            "changes to the network management stack.",
        ],
        diagnostics=(
            "DTCs for routing table checksum mismatch, time sync loss and security "
            "verification failure are defined in the diagnostics specification. The "
            "HLD only defines the reporting path: component to Dcm to CanIf."
        ),
        limitations=(
            "Routing tables are static in revision A; dynamic reconfiguration "
            "requires secure OTA support not covered here."
        ),
    ),
    DomainSpec(
        system_name="Diagnostics and Service System",
        doc_id="DIAG-HLD-0015",
        revision="B",
        title="Diagnostics and Service High-Level Design (HLD)",
        summary=(
            "This document describes the software architecture of the diagnostics "
            "and service domain: UDS service handling, fault memory management, "
            "routine control and over-the-air update components and interfaces."
        ),
        scope=(
            "The diagnostics domain covers UDS service dispatch, DTC storage and "
            "retrieval, routine execution and secure over-the-air update staging. "
            "Out of scope: tester application design and production flash programming "
            "hardware details."
        ),
        context=(
            "The domain runs on DiagnosticsEcu connected to all other ECUs through "
            "the central gateway over DoIP and CAN."
        ),
        components=[
            ["UdsServiceDispatcher", "ApplicationSwComponentType", "UDS service request routing"],
            ["FaultMemoryManager", "ApplicationSwComponentType", "DTC storage and aging"],
            ["RoutineControlManager", "ApplicationSwComponentType", "Diagnostic routine execution"],
            ["OtaUpdateStager", "ApplicationSwComponentType", "Over-the-air package staging"],
            ["SecurityAccessManager", "ApplicationSwComponentType", "UDS security access levels"],
            ["DiagSignalService", "ServiceSwComponentType", "Diagnostics signal service"],
            ["DiagGatewayAbstraction", "EcuAbstractionSwComponentType", "Diagnostic gateway abstraction"],
            ["DiagnosticsMainComposition", "CompositionSwComponentType", "Composition of the diagnostics components"],
        ],
        ports=[
            ["UdsRequestIn", "required", "UdsRequestI", "UdsServiceDispatcher"],
            ["DtcStatusOut", "provided", "DtcStatusI", "FaultMemoryManager"],
            ["RoutineResultOut", "provided", "RoutineResultI", "RoutineControlManager"],
            ["OtaProgressOut", "provided", "OtaProgressI", "OtaUpdateStager"],
            ["SecurityTokenOut", "provided", "SecurityTokenI", "SecurityAccessManager"],
            ["DiagGatewayIn", "required", "DiagSignalSetI", "DiagSignalService"],
            ["GatewayToTester", "provided", "DiagRoutingI", "DiagGatewayAbstraction"],
            ["FaultSnapshotOut", "provided", "FaultSnapshotI", "FaultMemoryManager"],
        ],
        signals=[
            ["UdsResponseCode", "UdsRequestI", "UdsServiceDispatcher", "DiagGatewayAbstraction", "8"],
            ["ActiveDtcCount", "DtcStatusI", "FaultMemoryManager", "UdsServiceDispatcher", "8"],
            ["RoutineStatus", "RoutineResultI", "RoutineControlManager", "FaultMemoryManager", "4"],
            ["UpdateProgress", "OtaProgressI", "OtaUpdateStager", "UdsServiceDispatcher", "8"],
            ["SecurityLevel", "SecurityTokenI", "SecurityAccessManager", "OtaUpdateStager", "4"],
            ["FaultSnapshotData", "FaultSnapshotI", "FaultMemoryManager", "RoutineControlManager", "32"],
            ["TesterPresent", "TesterPresentI", "DiagGatewayAbstraction", "UdsServiceDispatcher", "1"],
        ],
        flows=[
            (
                "UDS service flow",
                "UdsServiceDispatcher consumes UdsRequestIn from the tester through "
                "GatewayToTester, validates SecurityLevel via SecurityAccessManager "
                "and dispatches to FaultMemoryManager or RoutineControlManager as "
                "required. UdsResponseCode is returned to the tester.",
            ),
            (
                "Fault memory flow",
                "FaultMemoryManager stores confirmed DTCs with FaultSnapshotData and "
                "ages them over drive cycles. ActiveDtcCount is published to "
                "UdsServiceDispatcher for ReadDTCInformation services.",
            ),
            (
                "OTA staging flow",
                "OtaUpdateStager receives a signed update package, validates it with "
                "SecurityAccessManager and stages it in the standby flash bank. "
                "UpdateProgress is reported to the tester until activation completes.",
            ),
        ],
        timing=(
            "TimingEvent UdsDispatchEvent triggers DispatchUdsRequestRunnable every "
            "10 ms. TimingEvent FaultAgingEvent triggers AgeFaultMemoryRunnable every "
            "1000 ms. TimingEvent OtaVerifyEvent triggers VerifyOtaPackageRunnable "
            "every 200 ms. All runnables are scheduled by DiagTask on DiagnosticsEcu."
        ),
        bsw=[
            "Signal routing uses Com and PduR. Incoming DoIP requests are handled by "
            "SoAd and TcpIp. NvM stores the DTC memory and security seeds. Rte "
            "provides the port API used by all diagnostics application components.",
            "Mode management is performed by BswM and EcuM. Watchdog supervision for "
            "DiagTask is performed by WdgM. Flash access for OTA staging uses Fls "
            "through the memory abstraction.",
            "The diagnostic path routes UDS requests through Dcm and Dem. "
            "DiagSignalService consumes DiagSignalSetI and forwards session state "
            "changes to the network management stack.",
        ],
        diagnostics=(
            "DTCs for diagnostic session timeout, security access violation and OTA "
            "package verification failure are defined in the diagnostics "
            "specification. The HLD defines the internal reporting path: component to "
            "Dcm to SoAd."
        ),
        limitations=(
            "OtaUpdateStager supports a single standby flash bank in this revision; "
            "dual-bank seamless update is planned for a later revision."
        ),
    ),
]


def build_domain_pdf(spec: DomainSpec, path: Path) -> None:
    builder = Builder()
    builder.title = spec.title

    builder.gap(120)
    builder.heading(spec.system_name, 1)
    builder.heading("High-Level Design (HLD)", 2)
    builder.gap(20)
    builder.para(f"Document ID: {spec.doc_id}")
    builder.para(f"Revision: {spec.revision}")
    builder.para("Status: Approved for engineering reference")
    builder.para("Classification: Confidential - internal engineering reference")
    builder.gap(30)
    builder.para(spec.summary)

    builder.heading("1 Revision history", 1)
    builder.table(
        ["Revision", "Date", "Author", "Description"],
        [[spec.revision, "2026-05-14", "A. Kumar", "Initial architecture baseline"]],
        [60, 80, 90, 265],
    )

    builder.heading("2 Scope and context", 1)
    builder.heading("2.1 Scope", 2)
    builder.para(spec.scope)
    builder.heading("2.2 System context", 2)
    builder.para(spec.context)

    builder.heading("3 Software architecture", 1)
    builder.heading("3.1 Component breakdown", 2)
    builder.table(["Component", "Type", "Description"], spec.components, [150, 165, 180])

    builder.heading("3.2 Ports and interfaces", 2)
    builder.table(["Port", "Direction", "Interface", "Component"], spec.ports, [130, 80, 145, 140])

    builder.heading("3.3 Signal inventory", 2)
    builder.table(
        ["Signal", "Interface", "Sender", "Receiver", "Bits"],
        spec.signals,
        [120, 120, 125, 115, 15],
    )

    builder.heading("4 Functional flows", 1)
    for index, (title, text) in enumerate(spec.flows, start=1):
        builder.heading(f"4.{index} {title}", 2)
        builder.para(text)

    builder.heading("5 Timing and runnables", 1)
    builder.para(spec.timing)

    builder.heading("6 Basic software integration", 1)
    for para in spec.bsw:
        builder.para(para)

    builder.heading("7 Diagnostics and configuration", 1)
    builder.para(spec.diagnostics)
    builder.para(
        "Configuration parameters are grouped into the domain configuration "
        "container and written through NvM during shutdown."
    )

    builder.heading("8 Known limitations", 1)
    builder.para(spec.limitations)

    builder.heading("9 Open questions", 1)
    builder.para(
        "Open: calibration ownership for cross-domain interfaces and the timeline "
        "for production software freeze are tracked outside this document."
    )

    builder.save(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate additional sample AUTOSAR HLD PDFs")
    parser.add_argument(
        "--outdir", default=str(Path(__file__).resolve().parent), help="Output directory"
    )
    args = parser.parse_args()
    outdir = Path(args.outdir)
    slug_names = [
        "hld_adas.pdf",
        "hld_powertrain.pdf",
        "hld_body_control.pdf",
        "hld_network_gateway.pdf",
        "hld_diagnostics.pdf",
    ]
    for spec, name in zip(SPECS, slug_names):
        path = outdir / name
        build_domain_pdf(spec, path)
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
