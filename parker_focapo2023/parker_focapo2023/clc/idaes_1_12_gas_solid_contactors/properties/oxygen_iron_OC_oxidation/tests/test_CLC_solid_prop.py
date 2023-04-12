#################################################################################
# The Institute for the Design of Advanced Energy Systems Integrated Platform
# Framework (IDAES IP) was produced under the DOE Institute for the
# Design of Advanced Energy Systems (IDAES), and is copyright (c) 2018-2021
# by the software owners: The Regents of the University of California, through
# Lawrence Berkeley National Laboratory,  National Technology & Engineering
# Solutions of Sandia, LLC, Carnegie Mellon University, West Virginia University
# Research Corporation, et al.  All rights reserved.
#
# Please see the files COPYRIGHT.md and LICENSE.md for full copyright and
# license information.
#################################################################################
"""
Tests for CLC solid phase thermo state block; tests for construction and solve
Author: Chinedu Okoli
"""

import pytest

from pyomo.environ import (
        ConcreteModel,
        TerminationCondition,
        SolverStatus,
        Var,
        Constraint,
        value,
        units as pyunits,
        )
import pyomo.common.unittest as unittest
from pyomo.common.collections import ComponentMap
from pyomo.util.subsystems import ParamSweeper
from pyomo.contrib.incidence_analysis import (
        solve_strongly_connected_components,
        )

from idaes.core import FlowsheetBlock

from idaes.core.util.model_statistics import (
        degrees_of_freedom,
        number_large_residuals,
        )

from idaes.core.util.testing import (get_default_solver,
                                     initialization_tester)

from parker_focapo2023.clc.idaes_1_12_gas_solid_contactors.properties.oxygen_iron_OC_oxidation. \
    solid_phase_thermo import SolidPhaseParameterBlock

# Get default solver for testing
solver = get_default_solver()


# -----------------------------------------------------------------------------
@pytest.fixture(scope="class")
def solid_prop():
    m = ConcreteModel()
    m.fs = FlowsheetBlock(default={"dynamic": False})

    # solid properties and state inlet block
    m.fs.properties = SolidPhaseParameterBlock()

    m.fs.unit = m.fs.properties.build_state_block(
        default={"parameters": m.fs.properties,
                 "defined_state": True})

    m.fs.unit.flow_mass.fix(1)
    m.fs.unit.particle_porosity.fix(0.27)
    m.fs.unit.temperature.fix(1183.15)
    m.fs.unit.mass_frac_comp["Fe2O3"].fix(0.244)
    m.fs.unit.mass_frac_comp["Fe3O4"].fix(0.202)
    m.fs.unit.mass_frac_comp["Al2O3"].fix(0.554)

    return m


def test_build_inlet_state_block(solid_prop):
    assert isinstance(solid_prop.fs.unit.dens_mass_skeletal, Var)
    assert isinstance(solid_prop.fs.unit.enth_mol_comp, Var)
    assert isinstance(solid_prop.fs.unit.enth_mass, Var)
    assert isinstance(solid_prop.fs.unit.cp_mol_comp, Var)
    assert isinstance(solid_prop.fs.unit.cp_mass, Var)


def test_setInputs_state_block(solid_prop):
    assert degrees_of_freedom(solid_prop.fs.unit) == 0


def test_initialize(solid_prop):
    initialization_tester(
            solid_prop)


def test_solve(solid_prop):

    assert hasattr(solid_prop.fs.unit, "dens_mass_skeletal")
    assert hasattr(solid_prop.fs.unit, "cp_mass")
    assert hasattr(solid_prop.fs.unit, "enth_mass")

    results = solver.solve(solid_prop)

    # Check for optimal solution
    assert results.solver.termination_condition == \
        TerminationCondition.optimal
    assert results.solver.status == SolverStatus.ok


def test_solution(solid_prop):
    assert (pytest.approx(3251.75, abs=1e-2) ==
            solid_prop.fs.unit.dens_mass_skeletal.value)
    assert (pytest.approx(1, abs=1e-2) ==
            solid_prop.fs.unit.cp_mass.value)
    assert (pytest.approx(0.0039, abs=1e-2) ==
            solid_prop.fs.unit.enth_mass.value)


def test_state_vars():
    m = ConcreteModel()
    m.fs = FlowsheetBlock(default={"dynamic": False})

    m.fs.properties = SolidPhaseParameterBlock()
    m.fs.state = m.fs.properties.build_state_block()

    assert isinstance(m.fs.state.flow_mass, Var)
    assert isinstance(m.fs.state.temperature, Var)
    assert isinstance(m.fs.state.particle_porosity, Var)
    assert isinstance(m.fs.state.mass_frac_comp, Var)

    assert isinstance(m.fs.state.sum_component_eqn, Constraint)

    assert len(list(m.fs.state.component_data_objects(Var))) == 6
    assert len(list(m.component_data_objects(Constraint))) == 1

    for name, var in m.fs.state.define_state_vars().items():
        assert name in m.fs.properties._metadata._properties


def test_indexed_state_block():
    m = ConcreteModel()
    m.fs = FlowsheetBlock(default={"dynamic": False})
    m.fs.properties = SolidPhaseParameterBlock()
    m.fs.state = m.fs.properties.build_state_block([1,2,3])

    assert len([v for v in m.component_data_objects(Var) if not v.fixed]) == 18
    assert len(list(m.component_data_objects(Constraint))) == 3

    for i, state in m.fs.state.items():
        assert isinstance(state.flow_mass, Var)
        assert isinstance(state.temperature, Var)
        assert isinstance(state.particle_porosity, Var)
        assert isinstance(state.mass_frac_comp, Var)

        assert isinstance(state.sum_component_eqn, Constraint)


def test_property_construction_ordered():
    m = ConcreteModel()
    m.fs = FlowsheetBlock(default={"dynamic": False})
    m.fs.properties = SolidPhaseParameterBlock()
    m.fs.state = m.fs.properties.build_state_block()

    # If we construct properties in this order, variables and constraints
    # will be added one at a time.
    matching = [
            ("dens_mass_skeletal", "density_skeletal_constraint"),
            ("dens_mass_particle", "density_particle_constraint"),
            ("cp_mol_comp", "cp_shomate_eqn"),
            ("cp_mass", "mixture_heat_capacity_eqn"),
            ("enth_mol_comp", "enthalpy_shomate_eqn"),
            ("enth_mass", "mixture_enthalpy_eqn"),
            ]

    state_vars = m.fs.state.define_state_vars()
    n_state_vars = len(state_vars)
    n_vars = len(m.fs.properties._metadata._properties)
    assert len(matching) == n_vars - n_state_vars

    nvar = len(list(m.fs.state.component_data_objects(Var)))
    ncon = len(list(m.component_data_objects(Constraint)))

    for varname, conname in matching:
        assert varname not in state_vars
        var = getattr(m.fs.state, varname)
        con = getattr(m.fs.state, conname)
        dim = len(var)
        nvar += dim
        ncon += dim
        assert dim == len(con)
        assert isinstance(var, Var)
        assert isinstance(con, Constraint)
        assert len(list(m.fs.state.component_data_objects(Var))) == nvar
        assert len(list(m.component_data_objects(Constraint))) == ncon


class TestProperties(unittest.TestCase):

    def _make_model(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": False})
        m.fs.properties = SolidPhaseParameterBlock()
        m.fs.state = m.fs.properties.build_state_block(default={
            "defined_state": True,
            })
        for var in m.fs.state.define_state_vars().values():
            var.fix()
        return m

    def test_dens_mass_skeletal(self):
        m = self._make_model()
        state = m.fs.state

        n_scen = 4
        state_values = {
                "flow_mass": [1.0*pyunits.kg/pyunits.s]*n_scen,
                "temperature": [1200.0*pyunits.K]*n_scen,
                "particle_porosity": [0.27]*n_scen,
                "mass_frac_comp[Fe2O3]": [1.0, 0.0, 0.0, 1.0/3.0],
                "mass_frac_comp[Fe3O4]": [0.0, 1.0, 0.0, 1.0/3.0],
                "mass_frac_comp[Al2O3]": [0.0, 0.0, 1.0, 1.0/3.0],
                }
        state_values = ComponentMap((state.find_component(name), values)
                for name, values in state_values.items())
        kgm3 = pyunits.kg/pyunits.m**3
        target_values = {
                "dens_mass_skeletal": [
                    5250.000*kgm3,
                    5000.000*kgm3,
                    3987.000*kgm3,
                    4678.061*kgm3,
                    ],
                }
        target_values = ComponentMap((state.find_component(name), values)
                for name, values in target_values.items())

        param_sweeper = ParamSweeper(
                n_scen,
                state_values,
                output_values=target_values,
                )
        with param_sweeper:
            for inputs, outputs in param_sweeper:
                solve_strongly_connected_components(state)

                assert number_large_residuals(state, tol=1e-8) == 0

                for var, val in inputs.items():
                    val = value(pyunits.convert(val, var.get_units()))
                    assert var.value == pytest.approx(value(val), abs=1e-3)

                for var, val in outputs.items():
                    val = value(pyunits.convert(val, var.get_units()))
                    assert var.value == pytest.approx(value(val), abs=1e-3)

    def test_dens_mass_particle(self):
        m = self._make_model()
        state = m.fs.state

        n_scen = 3
        state_values = {
                "flow_mass": [1.0*pyunits.kg/pyunits.s]*n_scen,
                "temperature": [1200.0*pyunits.K]*n_scen,
                "particle_porosity": [0.22, 0.27, 0.32],
                "mass_frac_comp[Fe2O3]": [1.0/3.0]*n_scen,
                "mass_frac_comp[Fe3O4]": [1.0/3.0]*n_scen,
                "mass_frac_comp[Al2O3]": [1.0/3.0]*n_scen,
                }
        state_values = ComponentMap((state.find_component(name), values)
                for name, values in state_values.items())
        kgm3 = pyunits.kg/pyunits.m**3
        target_values = {
                "dens_mass_particle": [
                    3648.888*kgm3,
                    3414.985*kgm3,
                    3181.081*kgm3,
                    ],
                }
        target_values = ComponentMap((state.find_component(name), values)
                for name, values in target_values.items())

        param_sweeper = ParamSweeper(
                n_scen,
                state_values,
                output_values=target_values,
                )
        with param_sweeper:
            for inputs, outputs in param_sweeper:
                solve_strongly_connected_components(state)

                # Check that we have eliminated infeasibility
                assert number_large_residuals(state, tol=1e-8) == 0

                # Sanity check that inputs have been set properly
                for var, val in inputs.items():
                    val = value(pyunits.convert(val, var.get_units()))
                    assert var.value == pytest.approx(value(val), abs=1e-3)

                for var, val in outputs.items():
                    val = value(pyunits.convert(val, var.get_units()))
                    assert var.value == pytest.approx(value(val), abs=1e-3)

    def test_cp(self):
        m = self._make_model()
        state = m.fs.state

        n_scen = 4
        K = pyunits.K
        state_values = {
                "flow_mass": [1.0*pyunits.kg/pyunits.s]*n_scen,
                "temperature": [1000.0*K, 1100*K, 1200*K, 1300*K],
                "particle_porosity": [0.27]*n_scen,
                "mass_frac_comp[Fe2O3]": [1.0/3.0]*n_scen,
                "mass_frac_comp[Fe3O4]": [1.0/3.0]*n_scen,
                "mass_frac_comp[Al2O3]": [1.0/3.0]*n_scen,
                }
        state_values = ComponentMap((state.find_component(name), values)
                for name, values in state_values.items())
        kJmolK = pyunits.kJ/pyunits.mol/pyunits.K
        kJkgK = pyunits.kJ/pyunits.kg/pyunits.K
        target_values = {
                "cp_mol_comp[Fe2O3]": [
                    0.1401*kJmolK,
                    0.1408*kJmolK,
                    0.1415*kJmolK,
                    0.1423*kJmolK,
                    ],
                "cp_mol_comp[Fe3O4]": [
                    0.2008*kJmolK,
                    0.2008*kJmolK,
                    0.2008*kJmolK,
                    0.2008*kJmolK,
                    ],
                "cp_mol_comp[Al2O3]": [
                    0.1249*kJmolK,
                    0.1268*kJmolK,
                    0.1285*kJmolK,
                    0.1299*kJmolK,
                    ],
                "cp_mass": [
                    0.9899*kJkgK,
                    0.9975*kJkgK,
                    1.0045*kJkgK,
                    1.0108*kJkgK,
                    ],
                }
        target_values = ComponentMap((state.find_component(name), values)
                for name, values in target_values.items())

        param_sweeper = ParamSweeper(
                n_scen,
                state_values,
                output_values=target_values,
                )
        with param_sweeper:
            for inputs, outputs in param_sweeper:
                solve_strongly_connected_components(state)

                # Check that we have eliminated infeasibility
                assert number_large_residuals(state, tol=1e-8) == 0

                # Sanity check that inputs have been set properly
                for var, val in inputs.items():
                    val = value(pyunits.convert(val, var.get_units()))
                    assert var.value == pytest.approx(value(val), abs=1e-3)

                for var, val in outputs.items():
                    val = value(pyunits.convert(val, var.get_units()))
                    assert var.value == pytest.approx(value(val), abs=1e-3)


    def test_enth(self):
        m = self._make_model()
        state = m.fs.state

        n_scen = 4
        K = pyunits.K
        state_values = {
                "flow_mass": [1.0*pyunits.kg/pyunits.s]*n_scen,
                "temperature": [1000.0*K, 1100*K, 1200*K, 1300*K],
                "particle_porosity": [0.27]*n_scen,
                "mass_frac_comp[Fe2O3]": [1.0/3.0]*n_scen,
                "mass_frac_comp[Fe3O4]": [1.0/3.0]*n_scen,
                "mass_frac_comp[Al2O3]": [1.0/3.0]*n_scen,
                }
        state_values = ComponentMap((state.find_component(name), values)
                for name, values in state_values.items())
        kJmol = pyunits.kJ/pyunits.mol
        kJkg = pyunits.kJ/pyunits.kg
        target_values = {
                "enth_mol_comp[Fe2O3]": [
                    101.043*kJmol,
                    115.086*kJmol,
                    129.198*kJmol,
                    143.385*kJmol,
                    ],
                "enth_mol_comp[Fe3O4]": [
                    147.591*kJmol,
                    167.674*kJmol,
                    187.757*kJmol,
                    207.841*kJmol,
                    ],
                "enth_mol_comp[Al2O3]": [
                    77.925*kJmol,
                    90.513*kJmol,
                    103.279*kJmol,
                    116.199*kJmol,
                    ],
                "enth_mass": [
                    678.156*kJkg,
                    777.534*kJkg,
                    877.640*kJkg,
                    978.408*kJkg,
                    ],
                }
        target_values = ComponentMap((state.find_component(name), values)
                for name, values in target_values.items())

        param_sweeper = ParamSweeper(
                n_scen,
                state_values,
                output_values=target_values,
                )
        with param_sweeper:
            for inputs, outputs in param_sweeper:
                solve_strongly_connected_components(state)

                # Check that we have eliminated infeasibility
                assert number_large_residuals(state, tol=1e-8) == 0

                # Sanity check that inputs have been set properly
                for var, val in inputs.items():
                    val = value(pyunits.convert(val, var.get_units()))
                    assert var.value == pytest.approx(value(val), abs=1e-3)

                for var, val in outputs.items():
                    val = value(pyunits.convert(val, var.get_units()))
                    assert var.value == pytest.approx(value(val), abs=1e-3)


if __name__ == "__main__":
    unittest.main()
