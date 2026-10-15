"""Generate a synthetic two-revision AUTOSAR HLD PDF for demos and tests.

The document is fictional. It intentionally contains a handful of design
inconsistencies so the checker rules can be demonstrated end to end.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pymupdf

PAGE_W, PAGE_H = 595, 842
MARGIN = 50
BODY_SIZE = 10.0
LINE_H = 14.0

REVISION_A = "A"
REVISION_B = "B"


class Builder:
    def __init__(self) -> None:
        self.doc = pymupdf.open()
        self.page: pymupdf.Page | None = None
        self.y = MARGIN
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
        self.page.insert_text(
            (MARGIN, self.y + size), text, fontsize=size, fontname="hebo"
        )
        self.y += size + 8

    def para(self, text: str) -> None:
        assert self.page is not None
        rect = pymupdf.Rect(MARGIN, self.y, PAGE_W - MARGIN, PAGE_H - MARGIN)
        remaining = self.page.insert_textbox(
            rect, text, fontsize=BODY_SIZE, fontname="helv", align=0
        )
        if remaining < 0:
            self._new_page()
            assert self.page is not None
            rect = pymupdf.Rect(MARGIN, self.y, PAGE_W - MARGIN, PAGE_H - MARGIN)
            remaining = self.page.insert_textbox(
                rect, text, fontsize=BODY_SIZE, fontname="helv", align=0
            )
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
        x0 = MARGIN
        x_positions = [x0]
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
                text = str(cell)[:max_chars]
                self.page.insert_text(
                    (left + 3, bottom - 4.5), text, fontsize=8.2, fontname=font
                )
            self.page.draw_line((x_positions[0], bottom), (x_positions[-1], bottom))
        for x in x_positions:
            self.page.draw_line((x, self.y), (x, self.y + total_h))
        self.page.draw_rect(
            pymupdf.Rect(x_positions[0], self.y, x_positions[-1], self.y + total_h),
            width=0.6,
        )
        self.y += total_h + 10

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.doc.set_metadata(
            {
                "title": f"Vehicle Motion Control HLD (Revision {self.current_revision})",
                "author": "Reference Solution Document",
                "subject": "AUTOSAR High-Level Design",
                "keywords": "AUTOSAR,HLD,architecture",
            }
        )
        self.doc.save(path)
        self.doc.close()

    current_revision = REVISION_A


def build_document(path: Path, revision: str) -> None:
    builder = Builder()
    builder.current_revision = revision

    # -- title ---------------------------------------------------------
    builder.gap(120)
    builder.heading("Vehicle Motion Control System", 1)
    builder.heading("High-Level Design (HLD)", 2)
    builder.gap(20)
    builder.para("Document ID: VMC-HLD-0001")
    builder.para(f"Revision: {revision}")
    builder.para("Status: Approved for pilot evaluation")
    builder.para("Classification: Confidential - internal engineering reference")
    builder.gap(30)
    builder.para(
        "This document describes the software architecture of the vehicle motion "
        "control domain: components, ports, interfaces, signals, functional flows "
        "and basic software integration."
    )

    # -- revision history ---------------------------------------------
    builder.heading("1 Revision history", 1)
    history_rows = [
        ["A", "2026-04-10", "R. Iyer", "Initial architecture baseline"],
        ["B", "2026-08-22", "R. Iyer", "Traction control extension, steering rename"],
    ]
    if revision == REVISION_A:
        history_rows = history_rows[:1]
    builder.table(["Revision", "Date", "Author", "Description"], history_rows, [60, 80, 90, 265])

    # -- scope ---------------------------------------------------------
    builder.heading("2 Scope and context", 1)
    builder.heading("2.1 Scope", 2)
    builder.para(
        "The vehicle motion control domain covers longitudinal and lateral motion "
        "commands: vehicle speed processing, brake intervention, steering angle "
        "handling and gateway exchange with the powertrain and body domains."
    )
    builder.para(
        "Out of scope: actuator calibration values, production software details and "
        "hardware pin mapping. Those are covered by separate interface specifications."
    )
    if revision == REVISION_B:
        builder.heading("2.2 Traction control context", 2)
        builder.para(
            "Revision B adds an advisory traction control assist path that reuses the "
            "existing chassis gateway and brake arbitration components."
        )
    builder.heading("2.3 System context", 2)
    builder.para(
        "The domain runs on BodyEcu and ChassisEcu. Gateway exchange with the "
        "powertrain domain is performed by PowertrainGateway over the chassis CAN bus."
    )

    # -- components ----------------------------------------------------
    builder.heading("3 Software architecture", 1)
    builder.heading("3.1 Component breakdown", 2)
    components = [
        ["VehicleSpeedManager", "ApplicationSwComponentType", "Filters and plausibilises wheel speed input"],
        ["BrakeController", "ApplicationSwComponentType", "Brake torque arbitration and distribution"],
        ["SteeringAngleReader", "ApplicationSwComponentType", "Steering angle preprocessing"],
        ["ChassisSignalService", "ServiceSwComponentType", "Chassis signal gateway service"],
        ["PowertrainGateway", "EcuAbstractionSwComponentType", "Powertrain domain gateway"],
        ["BodyControlAdapter", "ApplicationSwComponentType", "Body electronics adaptation"],
        ["DiagnosticsFrontend", "ApplicationSwComponentType", "Diagnostic services front end"],
        ["VehicleMotionComposition", "CompositionSwComponentType", "Composition of the domain components"],
    ]
    if revision == REVISION_B:
        components[2] = [
            "SteeringAnglePreprocessor",
            "ApplicationSwComponentType",
            "Steering angle preprocessing and filtering",
        ]
        components.append(
            ["TractionControlAssist", "ApplicationSwComponentType", "Advisory traction control assist"]
        )
    builder.table(["Component", "Type", "Description"], components, [150, 165, 180])

    # -- ports ---------------------------------------------------------
    builder.heading("3.2 Ports and interfaces", 2)
    ports = [
        ["VehicleSpeedOut", "provided", "VehicleSpeedI", "VehicleSpeedManager"],
        ["WheelSpeedIn", "required", "WheelSpeedI", "VehicleSpeedManager"],
        ["BrakePressureOut", "provided", "BrakePressureI", "BrakeController"],
        ["SteerAngleOut", "provided", "SteeringAngleI", "SteeringAngleReader"],
        ["ChassisGatewayIn", "required", "ChassisSignalSetI", "ChassisSignalService"],
        ["GatewayToPowertrain", "provided", "PowertrainExchangeI", "PowertrainGateway"],
        ["LampCommandOut", "provided", "LampCommandI", "BodyControlAdapter"],
        ["DiagRequestIn", "required", "DiagnosticServiceI", "DiagnosticsFrontend"],
    ]
    if revision == REVISION_B:
        ports[3][3] = "SteeringAnglePreprocessor"
        ports.append(
            ["TractionRequestOut", "provided", "TractionRequestI", "TractionControlAssist"]
        )
    builder.table(["Port", "Direction", "Interface", "Component"], ports, [130, 80, 145, 140])

    builder.para(
        "VehicleSpeedOut port is provided by VehicleSpeedManager and consumed by "
        "PowertrainGateway. SteeringAngleOut is required by BrakeController for "
        "lateral stability arbitration."
    )
    builder.para(
        "PowertrainGateway requires VehicleSpeedOut at 10 ms to update the gateway "
        "frame, and requires GearPosition for the shift intervention path."
    )
    if revision == REVISION_B:
        builder.para(
            "The Chassis_SignalService gateway keeps its legacy spelling in the "
            "powertrain gateway mapping table."
        )

    # -- signals -------------------------------------------------------
    builder.heading("3.3 Signal inventory", 2)
    signals = [
        ["VehicleSpeed", "VehicleSpeedI", "VehicleSpeedManager", "PowertrainGateway", "16"],
        ["WheelSpeedFL", "WheelSpeedI", "ChassisSignalService", "VehicleSpeedManager", "16"],
        ["WheelSpeedFR", "WheelSpeedI", "ChassisSignalService", "VehicleSpeedManager", "16"],
        ["BrakePressure", "BrakePressureI", "BrakeController", "DiagnosticsFrontend", "12"],
        ["SteeringAngle", "SteeringAngleI", "SteeringAngleReader", "BrakeController", "12"],
        ["GearPosition", "GearPositionI", "PowertrainGateway", "BodyControlAdapter", "8"],
        ["LampCommand", "LampCommandI", "BodyControlAdapter", "DiagnosticsFrontend", "8"],
    ]
    if revision == REVISION_B:
        signals[4][2] = "SteeringAnglePreprocessor"
        signals.append(
            ["TractionRequest", "TractionRequestI", "TractionControlAssist", "BrakeController", "8"]
        )
    builder.table(
        ["Signal", "Interface", "Sender", "Receiver", "Bits"], signals, [120, 120, 125, 115, 15]
    )

    # -- functional flows ---------------------------------------------
    builder.heading("4 Functional flows", 1)
    builder.heading("4.1 Vehicle speed flow", 2)
    builder.para(
        "WheelSpeedFL and WheelSpeedFR arrive via ChassisSignalService and are "
        "consumed by VehicleSpeedManager. VehicleSpeedManager uses "
        "WheelSpeedSensorAdapter for plausibility checks before publishing "
        "VehicleSpeed through the VehicleSpeedI interface."
    )
    builder.para(
        "PowertrainGateway receives VehicleSpeed and republishes it to the powertrain "
        "domain. The same value is requested by DiagnosticsFrontend for read data by "
        "identifier services."
    )
    builder.heading("4.2 Brake intervention flow", 2)
    builder.para(
        "BrakeController requires BrakePressureI from the brake pedal path and "
        "receives SteeringAngle from SteeringAngleReader. When the stability "
        "threshold is exceeded, BrakeController requests torque reduction from "
        "PowertrainGateway through PowertrainExchangeI."
    )
    if revision == REVISION_B:
        builder.heading("4.3 Traction control flow", 2)
        builder.para(
            "TractionControlAssist publishes TractionRequest over TractionRequestI. "
            "BrakeController consumes the request and applies wheel individual "
            "braking. TorqueVectoringBlock uses TractionControlUnit to coordinate "
            "the advisory torque limit with the powertrain domain."
        )
        builder.para(
            "BodyControlAdapter raises AmberWarningSignal while the assist function "
            "is active, and clears the lamp once the request is released."
        )
    else:
        builder.para(
            "BodyControlAdapter raises AmberWarningSignal while the stability "
            "intervention is active, and clears the lamp once the vehicle speed "
            "plausibility check passes again."
        )

    # -- timing --------------------------------------------------------
    builder.heading("5 Timing and runnables", 1)
    builder.para(
        "TimingEvent VehicleSpeedSampleEvent triggers RunnableEntity "
        "UpdateVehicleSpeedRunnable every 10 ms. TimingEvent BrakeCheckEvent "
        "triggers EvaluateBrakePressureRunnable every 20 ms."
    )
    builder.para(
        "Both runnables are scheduled by MotionTask on ChassisEcu. The composition "
        "runnable ComposeVehicleMotionRunnable executes after the sensor runnables "
        "and before the gateway runnable PublishGatewayValuesRunnable."
    )

    # -- bsw -----------------------------------------------------------
    builder.heading("6 Basic software integration", 1)
    builder.para(
        "Signal routing uses Com and PduR. Incoming frames are handled by CanIf on "
        "both ECUs. NvM stores the calibration block for the speed plausibility "
        "window. Rte provides the port API used by all application components."
    )
    builder.para(
        "Mode management is performed by BswM and EcuM. Watchdog supervision for "
        "MotionTask is performed by WdgM. The chassis gateway maps IPdu to NPdu "
        "inside PowertrainGateway before transmission."
    )
    builder.para(
        "The diagnostic path routes UDS requests through Dcm and Dem. "
        "DiagnosticsFrontend consumes DiagnosticServiceI and forwards "
        "routine results to the tester."
    )

    # -- diagnostics ---------------------------------------------------
    builder.heading("7 Diagnostics and configuration", 1)
    builder.para(
        "DTCs for speed plausibility, brake pressure range and gateway timeout are "
        "defined in the diagnostics specification. The HLD only defines the reporting "
        "path: component to Dcm to CanIf."
    )
    builder.para(
        "Configuration parameters are grouped into the VMC configuration container "
        "and written through NvM during shutdown."
    )

    # -- intentionally thin sections (checker demo) ---------------------
    builder.page_break()
    builder.heading("8 Known limitations", 1)
    builder.para("TBD.")

    if revision == REVISION_A:
        builder.page_break()
        builder.heading("9 Open questions", 1)

    builder.save(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate sample AUTOSAR HLD PDFs")
    parser.add_argument(
        "--outdir", default=str(Path(__file__).resolve().parent), help="Output directory"
    )
    args = parser.parse_args()
    outdir = Path(args.outdir)
    build_document(outdir / "hld_revision_a.pdf", REVISION_A)
    build_document(outdir / "hld_revision_b.pdf", REVISION_B)
    print(f"Wrote {outdir / 'hld_revision_a.pdf'}")
    print(f"Wrote {outdir / 'hld_revision_b.pdf'}")


if __name__ == "__main__":
    main()
