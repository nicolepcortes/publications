##############################################################################
# Institute for the Design of Advanced Energy Systems Process Systems
# Engineering Framework (IDAES PSE Framework) Copyright (c) 2018, by the
# software owners: The Regents of the University of California, through
# Lawrence Berkeley National Laboratory,  National Technology & Engineering
# Solutions of Sandia, LLC, Carnegie Mellon University, West Virginia
# University Research Corporation, et al. All rights reserved.
#
# Please see the files COPYRIGHT.txt and LICENSE.txt for full copyright and
# license information, respectively. Both files are also available online
# at the URL "https://github.com/IDAES/idaes".
##############################################################################
"""
unit operation model for a steam heater applicable to platen superheater and roof superheater
main equations:
    Heat is given by fire-side boiler model
    Calculate pressure change due to friction
    Calculate slag layer wall temperature
    Consider a layer of metal and a layer of slag

Created: March 2019 by Jinliang Ma
@JinliangMa: jinliang.ma@netl.doe.gov
"""

# Import Python libraries
import math

# Import Pyomo libraries
from pyomo.common.config import ConfigBlock, ConfigValue, In

# Import IDAES cores
from idaes.core import (ControlVolume0DBlock,
                        declare_process_block_class,
                        MaterialBalanceType,
                        EnergyBalanceType,
                        MomentumBalanceType,
                        UnitModelBlockData,
                        useDefault)

from idaes.core.util.config import (is_physical_parameter_block,
                                    is_reaction_parameter_block)
from idaes.core.util.misc import add_object_reference
import idaes.logger as idaeslog


# Additional import for the unit operation
from pyomo.environ import SolverFactory, value, Var, Param, asin, cos, sqrt, log10
from pyomo.opt import TerminationCondition
from pyomo.core.expr.current import Expr_if
from pyomo.dae import DerivativeVar
import idaes.core.util.scaling as iscale


__author__ = "Jinliang Ma <jinliang.ma.doe.gov>"
__version__ = "2.0.0"


@declare_process_block_class("SteamHeater")
class SteamHeaterData(UnitModelBlockData):
    """
    WaterwallSection Unit Class
    """
    CONFIG = ConfigBlock()
    CONFIG.declare("dynamic", ConfigValue(
        domain=In([useDefault, True, False]),
        default=useDefault,
        description="Dynamic model flag",
        doc="""Indicates whether this model will be dynamic or not,
**default** = useDefault.
**Valid values:** {
**useDefault** - get flag from parent (default = False),
**True** - set as a dynamic model,
**False** - set as a steady-state model.}"""))
    CONFIG.declare("has_holdup", ConfigValue(
        default=False,
        domain=In([True, False]),
        description="Holdup construction flag",
        doc="""Indicates whether holdup terms should be constructed or not.
Must be True if dynamic = True,
**default** - False.
**Valid values:** {
**True** - construct holdup terms,
**False** - do not construct holdup terms}"""))
    CONFIG.declare("material_balance_type", ConfigValue(
        default=MaterialBalanceType.componentPhase,
        domain=In(MaterialBalanceType),
        description="Material balance construction flag",
        doc="""Indicates what type of material balance should be constructed,
**default** - MaterialBalanceType.componentPhase.
**Valid values:** {
**MaterialBalanceType.none** - exclude material balances,
**MaterialBalanceType.componentPhase** - use phase component balances,
**MaterialBalanceType.componentTotal** - use total component balances,
**MaterialBalanceType.elementTotal** - use total element balances,
**MaterialBalanceType.total** - use total material balance.}"""))
    CONFIG.declare("energy_balance_type", ConfigValue(
        default=EnergyBalanceType.enthalpyTotal,
        domain=In(EnergyBalanceType),
        description="Energy balance construction flag",
        doc="""Indicates what type of energy balance should be constructed,
**default** - EnergyBalanceType.enthalpyTotal.
**Valid values:** {
**EnergyBalanceType.none** - exclude energy balances,
**EnergyBalanceType.enthalpyTotal** - single ethalpy balance for material,
**EnergyBalanceType.enthalpyPhase** - ethalpy balances for each phase,
**EnergyBalanceType.energyTotal** - single energy balance for material,
**EnergyBalanceType.energyPhase** - energy balances for each phase.}"""))
    CONFIG.declare("momentum_balance_type", ConfigValue(
        default=MomentumBalanceType.pressureTotal,
        domain=In(MomentumBalanceType),
        description="Momentum balance construction flag",
        doc="""Indicates what type of momentum balance should be constructed,
**default** - MomentumBalanceType.pressureTotal.
**Valid values:** {
**MomentumBalanceType.none** - exclude momentum balances,
**MomentumBalanceType.pressureTotal** - single pressure balance for material,
**MomentumBalanceType.pressurePhase** - pressure balances for each phase,
**MomentumBalanceType.momentumTotal** - single momentum balance for material,
**MomentumBalanceType.momentumPhase** - momentum balances for each phase.}"""))
    CONFIG.declare("has_heat_transfer", ConfigValue(
        default=False,
        domain=In([True, False]),
        description="Heat transfer term construction flag",
        doc="""Indicates whether terms for heat transfer should be constructed,
**default** - False.
**Valid values:** {
**True** - include heat transfer terms,
**False** - exclude heat transfer terms.}"""))
    CONFIG.declare("has_pressure_change", ConfigValue(
        default=False,
        domain=In([True, False]),
        description="Pressure change term construction flag",
        doc="""Indicates whether terms for pressure change should be
constructed,
**default** - False.
**Valid values:** {
**True** - include pressure change terms,
**False** - exclude pressure change terms.}"""))
    CONFIG.declare("has_equilibrium_reactions", ConfigValue(
        default=True,
        domain=In([True, False]),
        description="Equilibrium reaction construction flag",
        doc="""Indicates whether terms for equilibrium controlled reactions
should be constructed,
**default** - True.
**Valid values:** {
**True** - include equilibrium reaction terms,
**False** - exclude equilibrium reaction terms.}"""))
    CONFIG.declare("has_heat_of_reaction", ConfigValue(
        default=False,
        domain=In([True, False]),
        description="Heat of reaction term construction flag",
        doc="""Indicates whether terms for heat of reaction terms should be
constructed,
**default** - False.
**Valid values:** {
**True** - include heat of reaction terms,
**False** - exclude heat of reaction terms.}"""))
    CONFIG.declare("property_package", ConfigValue(
        default=useDefault,
        domain=is_physical_parameter_block,
        description="Property package to use for control volume",
        doc="""Property parameter object used to define property calculations,
**default** - useDefault.
**Valid values:** {
**useDefault** - use default package from parent model or flowsheet,
**PhysicalParameterObject** - a PhysicalParameterBlock object.}"""))
    CONFIG.declare("property_package_args", ConfigBlock(
        implicit=True,
        description="Arguments to use for constructing property packages",
        doc="""A ConfigBlock with arguments to be passed to a property block(s)
and used when constructing these,
**default** - None.
**Valid values:** {
see property package for documentation.}"""))
    CONFIG.declare("reaction_package", ConfigValue(
        default=None,
        domain=is_reaction_parameter_block,
        description="Reaction package to use for control volume",
        doc="""Reaction parameter object used to define reaction calculations,
**default** - None.
**Valid values:** {
**None** - no reaction package,
**ReactionParameterBlock** - a ReactionParameterBlock object.}"""))
    CONFIG.declare("reaction_package_args", ConfigBlock(
        implicit=True,
        description="Arguments to use for constructing reaction packages",
        doc="""A ConfigBlock with arguments to be passed to a reaction block(s)
and used when constructing these,
**default** - None.
**Valid values:** {
see reaction package for documentation.}"""))
    CONFIG.declare("single_side_only", ConfigValue(
        default=True,
        domain=In([True, False]),
        description="Flag indicating the heat is from one side of tubes only",
        doc="""Indicates whether tubes are heated from one side only,
**default** - True.
**Valid values:** {
**True** - single side is heated such as roof,
**False** - both sides are heated such as platen superheater.}"""))
    def build(self):
        """
        Begin building model (pre-DAE transformation)


        Args:
            None

        Returns:
            None
        """
        # Call UnitModel.build to setup dynamics
        super(SteamHeaterData, self).build()

        # Build Control Volume
        self.control_volume = ControlVolume0DBlock(default={
                "dynamic": self.config.dynamic,
                "has_holdup": self.config.has_holdup,
                "property_package": self.config.property_package,
                "property_package_args": self.config.property_package_args})

        self.control_volume.add_geometry()

        self.control_volume.add_state_blocks(has_phase_equilibrium=False)

        self.control_volume.add_material_balances(
            balance_type=self.config.material_balance_type,
            has_rate_reactions=False,
            has_equilibrium_reactions=False)

        self.control_volume.add_energy_balances(
            balance_type=self.config.energy_balance_type,
            has_heat_of_reaction=False,
            has_heat_transfer=self.config.has_heat_transfer)

        self.control_volume.add_momentum_balances(
            balance_type=self.config.momentum_balance_type,
            has_pressure_change=True)

        # Add Ports
        self.add_inlet_port()
        self.add_outlet_port()

        # Add object references
        add_object_reference(self,
                             "volume",
                             self.control_volume.volume)

        # Set references to balance terms at unit level
        if (self.config.has_heat_transfer is True and
                self.config.energy_balance_type != EnergyBalanceType.none):
            add_object_reference(self, "heat_duty", self.control_volume.heat)

        if (self.config.has_pressure_change is True and
                self.config.momentum_balance_type != 'none'):
            add_object_reference(self, "deltaP", self.control_volume.deltaP)

        # Set Unit Geometry and Holdup Volume
        self._set_geometry()

        # Construct performance equations
        self._make_performance()


    def _set_geometry(self):
        """
        Define the geometry of the unit as necessary, and link to holdup volume
        """

        # Constant pi
        self.pi = Param(
                initialize=math.pi,
                doc="Pi")
        # Number of tubes that steam flows through
        self.count = Var(
                initialize=4,
                doc="Number of tubes")
        # Average length of tubes that steam flows through from inlet to outlet
        self.length_tube = Var(
                initialize=5.0,
                doc="length tube from inlet to outlet")
       # Inside diameter of tubes
        self.diameter_in = Var(
                initialize=0.05,
                doc="Inside diameter of tubes")
        # Inside radius of tube
        @self.Expression(doc="Inside radius of tube")
        def radius_in(b):
            return 0.5*b.diameter_in
        # Total cross section area of fluid flow
        @self.Expression(doc="Cross section area of fluid")
        def area_cross_fluid_total(b):
            return 0.25*b.pi*b.diameter_in**2*b.count
        # Tube thickness
        self.thk_tube = Var(
                initialize=0.005,
                doc="Thickness of tube")
        # Outside radius of tube
        @self.Expression(doc="Outside radius of tube")
        def radius_out(b):
            return b.radius_in + b.thk_tube
        # Thickness of fin
        self.thk_fin = Var(
                initialize=0.004,
                doc="Thickness of fin")
        # Half of fin thickness
        @self.Expression(doc="Half of fin thickness")
        def thk_fin_half(b):
            return 0.5*b.thk_fin
        # Length of fin
        self.length_fin = Var(
                initialize=0.005,
                doc="Length of fin")
        # Thickness of slag layer
        self.thk_slag = Var(
                self.flowsheet().config.time,
                initialize=0.001,
                doc="thickness of slag layer")
        @self.Expression(doc="Pitch of two neighboring tubes")
        def pitch(b):
            return b.length_fin + b.radius_out*2.0
        # total projected area
        @self.Expression(doc="total projected area for heat transfer")
        def area_proj_total(b):
            if self.config.single_side_only:
                return b.length_tube * b.pitch * b.count
            else:
                return 2*b.length_tube * b.pitch * b.count
        @self.Expression(doc="Angle at joint of tube and fin")
        def alpha_tube(b):
            return asin(b.thk_fin_half/b.radius_out)
        @self.Expression(self.flowsheet().config.time, doc="Angle at joint of tube and fin at outside slag layer")
        def alpha_slag(b, t):
            return asin((b.thk_fin_half+b.thk_slag[t])/(b.radius_out+b.thk_slag[t]))
        @self.Expression(doc="Perimeter of interface between slag and tube")
        def perimeter_if(b):
            if self.config.single_side_only:
                return (b.pi-2*b.alpha_tube)*b.radius_out + b.pitch - 2*b.radius_out*cos(b.alpha_tube)
            else:
                return 2*((b.pi-2*b.alpha_tube)*b.radius_out + b.pitch - 2*b.radius_out*cos(b.alpha_tube))
        @self.Expression(doc="Perimeter on the inner tube side")
        def perimeter_ts(b):
            return b.pi*b.diameter_in
        @self.Expression(self.flowsheet().config.time, doc="Perimeter on the outer slag side")
        def perimeter_ss(b, t):
            if self.config.single_side_only:
                return (b.pi-2*b.alpha_slag[t])*(b.radius_out+b.thk_slag[t]) + \
                       b.pitch - 2*(b.radius_out+b.thk_slag[t])*cos(b.alpha_slag[t])
            else:
                return 2*((b.pi-2*b.alpha_slag[t])*(b.radius_out+b.thk_slag[t]) + \
                       b.pitch - 2*(b.radius_out+b.thk_slag[t])*cos(b.alpha_slag[t]))
        # Cross section area of tube and fin metal
        @self.Expression(doc="Cross section area of tube and fin metal")
        def area_cross_metal(b):
            return b.pi*(b.radius_out**2-b.radius_in**2) + b.thk_fin*b.length_fin
        # Cross section area of slag layer
        @self.Expression(self.flowsheet().config.time, doc="Cross section area of slag layer per tube")
        def area_cross_slag(b, t):
            return b.perimeter_if*b.thk_slag[t]
        # Volume constraint
        @self.Constraint(self.flowsheet().config.time, doc="waterwall fluid volume of all tubes")
        def volume_eqn(b, t):
            return b.volume[t] == 0.25*b.pi*b.diameter_in**2*b.length_tube*b.count


    def _make_performance(self):
        """
        Define constraints which describe the behaviour of the unit model.
        """
        # Thermal conductivity of metal
        self.therm_cond_metal = Param(
                initialize=43.0,
                mutable=True,
                doc='Thermal conductivity of tube metal')
        # Thermal conductivity of slag
        self.therm_cond_slag = Param(
                initialize=1.3,
                mutable=True,
                doc='Thermal conductivity of slag')
        # Heat capacity of metal
        self.cp_metal = Param(
                initialize=500.0,
                mutable=True,
                doc='Heat capacity of tube metal')
        # Heat Capacity of slag
        self.cp_slag = Param(
                initialize=250,
                mutable=True,
                doc='Heat capacity of slag')
        # Density of metal
        self.dens_metal = Param(
                initialize=7800.0,
                mutable=True,
                doc='Density of tube metal')
        # Density of slag
        self.dens_slag = Param(
                initialize=2550,
                mutable=True,
                doc='Density of slag')
        # Shape factor of tube metal conduction
        self.fshape_metal = Param(
                initialize=1.0,
                mutable=True,
                doc='Shape factor of tube metal conduction')
        # Shape factor of slag conduction
        self.fshape_slag = Param(
                initialize=1.0,
                mutable=True,
                doc='Shape factor of slag conduction')

        # Add performance variables
        # Heat from fire side boiler model
        self.heat_fireside = Var(
                self.flowsheet().config.time,
                initialize=1e7,
                doc='total heat from fire side model for the section')
        # Tube boundary wall temperature
        self.temp_tube_boundary = Var(
                self.flowsheet().config.time,
                initialize=400.0,
                doc='Temperature of tube boundary wall')
        # Tube center point wall temperature
        self.temp_tube_center = Var(
                self.flowsheet().config.time,
                initialize=450.0,
                doc='Temperature of tube center wall')
        # Slag boundary wall temperature
        self.temp_slag_boundary = Var(
                self.flowsheet().config.time,
                initialize=600.0,
                doc='Temperature of slag boundary wall')
        # Slag center point slag wall temperature
        self.temp_slag_center = Var(
                self.flowsheet().config.time,
                initialize=500.0,
                doc='Temperature of slag layer center point')

        # Energy holdup for slag layer
        self.energy_holdup_slag = Var(
                self.flowsheet().config.time,
                initialize=1.0,
                doc='Energy holdup of slag layer')

        # Energy holdup for metal (tube + fin)
        self.energy_holdup_metal = Var(
                self.flowsheet().config.time,
                initialize=1.0,
                doc='Energy holdup of metal')

        # Energy accumulation for slag and metal
        if self.config.dynamic is True:
                self.energy_accumulation_slag = DerivativeVar(
                        self.energy_holdup_slag,
                        wrt=self.flowsheet().config.time,
                        doc='Energy accumulation of slag layer')
                self.energy_accumulation_metal = DerivativeVar(
                        self.energy_holdup_metal,
                        wrt=self.flowsheet().config.time,
                        doc='Energy accumulation of tube and fin metal')

        def energy_accumulation_term_slag(b, t):
            return b.energy_accumulation_slag[t] if b.config.dynamic else 0

        def energy_accumulation_term_metal(b, t):
            return b.energy_accumulation_metal[t] if b.config.dynamic else 0

        # Velocity of steam
        self.velocity = Var(
                self.flowsheet().config.time,
                initialize=3.0,
                doc='Velocity of steam')

        # Reynolds number based on liquid only flow
        self.N_Re = Var(
                self.flowsheet().config.time,
                initialize=1.0e6,
                doc='Reynolds number')

        # Prandtl number of liquid phase
        self.N_Pr = Var(
                self.flowsheet().config.time,
                initialize=2.0,
                doc='Reynolds number')

        # Darcy friction factor
        self.friction_factor_darcy = Var(
                self.flowsheet().config.time,
                initialize=0.01,
                doc='Darcy friction factor')

        # Convective heat transfer coefficient on tube side, typically in range (1000, 5e5)
        self.hconv = Var(
                self.flowsheet().config.time,
                initialize=30000.0,
                doc='Convective heat transfer coefficient')

        # Convective heat flux to fluid
        self.heat_flux_conv = Var(
                self.flowsheet().config.time,
                initialize=7e4,
                doc='Convective heat flux to fluid')

        # Fire-side heat flux
        self.heat_flux_fireside = Var(
                self.flowsheet().config.time,
                initialize=100000.0,
                doc='Fireside heat flux to slag boundary')

        # Slag-tube interface heat flux
        self.heat_flux_interface = Var(
                self.flowsheet().config.time,
                initialize=100000.0,
                doc='Slag-tube interface heat flux')

        # Equation to calculate heat flux to slag boundary
        @self.Constraint(self.flowsheet().config.time, doc="heat flux at slag outer layer")
        def heat_flux_fireside_from_boiler_eqn(b, t):
            if self.config.single_side_only:
                return b.heat_flux_fireside[t] * b.area_proj_total * b.perimeter_ss[t] == \
                       b.heat_fireside[t] * b.pitch
            else:
                return b.heat_flux_fireside[t] * b.area_proj_total * b.perimeter_ss[t] == \
                       b.heat_fireside[t] * b.pitch * 2.0

        # Equation to calculate slag layer boundary temperature
        @self.Constraint(self.flowsheet().config.time, doc="slag layer boundary temperature")
        def slag_layer_boundary_temperature_eqn(b, t):
            return b.heat_flux_fireside[t] * 0.5 * b.thk_slag[t] == b.fshape_slag * \
                   b.therm_cond_slag * (b.temp_slag_boundary[t] - b.temp_slag_center[t])

        # Equation to calculate heat flux at the slag-metal interface
        @self.Constraint(self.flowsheet().config.time, doc="heat flux at slag-tube interface")
        def heat_flux_interface_eqn(b, t):
            return b.heat_flux_interface[t] * 0.5 * \
                   (b.thk_slag[t]/b.therm_cond_slag/b.fshape_slag + b.thk_tube/b.therm_cond_metal/b.fshape_metal) == \
                   b.temp_slag_center[t] - b.temp_tube_center[t]

        # Equation to calculate heat flux at tube boundary
        @self.Constraint(self.flowsheet().config.time, doc="convective heat flux at tube boundary")
        def heat_flux_conv_eqn(b, t):
            return b.heat_flux_conv[t] == \
                   b.hconv[t] * (b.temp_tube_boundary[t] - (b.control_volume.properties_in[t].temperature + \
                   b.control_volume.properties_out[t].temperature)/2.0)

        # Equation to calculate tube boundary wall temperature
        @self.Constraint(self.flowsheet().config.time, doc="tube bounary wall temperature")
        def temperature_tube_boundary_eqn(b, t):
            return b.heat_flux_conv[t] * 0.5 * b.thk_tube == b.fshape_metal * \
                   b.therm_cond_metal * (b.temp_tube_center[t] - b.temp_tube_boundary[t])

        # Equation to calculate energy holdup for slag layer per tube length
        @self.Constraint(self.flowsheet().config.time, doc="energy holdup for slag layer")
        def energy_holdup_slag_eqn(b, t):
            return b.energy_holdup_slag[t] == \
                   b.temp_slag_center[t]*b.cp_slag*b.dens_slag*b.area_cross_slag[t]

        # Equation to calculate energy holdup for metal (tube + fin) per tube length
        @self.Constraint(self.flowsheet().config.time, doc="energy holdup for metal")
        def energy_holdup_metal_eqn(b, t):
            return b.energy_holdup_metal[t] == \
                   b.temp_tube_center[t]*b.cp_metal*b.dens_metal*b.area_cross_metal

        # Energy balance for slag layer
        @self.Constraint(self.flowsheet().config.time, doc="energy balance for slag layer")
        def energy_balance_slag_eqn(b, t):
            return energy_accumulation_term_slag(b,t) == (
                b.heat_flux_fireside[t]*b.perimeter_ss[t] -
                b.heat_flux_interface[t]*b.perimeter_if)

        # Energy balance for metal
        @self.Constraint(self.flowsheet().config.time, doc="energy balance for metal")
        def energy_balance_metal_eqn(b, t):
            return energy_accumulation_term_metal(b,t) == (
                   b.heat_flux_interface[t]*b.perimeter_if -
                   b.heat_flux_conv[t]*b.perimeter_ts)

        # Expression to calculate slag/tube metal interface wall temperature
        @self.Expression(self.flowsheet().config.time, doc="Slag tube interface wall temperature")
        def temp_interface(b, t):
            return b.temp_tube_center[t] + b.heat_flux_interface[t]*0.5*b.thk_tube/b.therm_cond_metal/b.fshape_metal

        # Equations for calculate pressure drop and convective heat transfer coefficient
        # Equation for calculating velocity
        @self.Constraint(self.flowsheet().config.time, doc="Vecolity of fluid")
        def velocity_eqn(b, t):
            return 1e-3*b.velocity[t]*b.area_cross_fluid_total * \
                   b.control_volume.properties_in[t].dens_mol_phase["Vap"] \
                   == 1e-3*b.control_volume.properties_in[t].flow_mol

        # Equation for calculating Reynolds number if liquid only
        @self.Constraint(self.flowsheet().config.time, doc="Reynolds number")
        def Reynolds_number_eqn(b, t):
            return b.N_Re[t] * \
                   b.control_volume.properties_in[t].visc_d_phase["Vap"] == \
                   b.diameter_in * b.velocity[t] * \
                   b.control_volume.properties_in[t].dens_mass

        # Friction factor depending on laminar or turbulent flow
        @self.Constraint(self.flowsheet().config.time, doc="Darcy friction factor")
        def friction_factor_darcy_eqn(b, t):
            return Expr_if(b.N_Re[t] < 1187.384, b.friction_factor_darcy[t]*b.N_Re[t]/64.0, \
                   b.friction_factor_darcy[t]*b.N_Re[t]**0.25/0.3164)==1.0

        # Pressure change equation due to friction, -1/2*density*velocity^2*fD/diameter*length
        @self.Constraint(self.flowsheet().config.time, doc="pressure change due to friction")
        def pressure_change_eqn(b, t):
            return b.deltaP[t] * b.diameter_in == \
                   -0.5 * b.control_volume.properties_in[t].dens_mass * \
                   b.velocity[t]**2 * b.friction_factor_darcy[t] * b.length_tube

        # Total heat added to control_volume
        @self.Constraint(self.flowsheet().config.time, doc="total heat added to fluid control_volume")
        def heat_eqn(b, t):
            return b.heat_duty[t] == b.count * b.heat_flux_conv[t] * b.length_tube * b.perimeter_ts

        # Prandtl number of steam
        @self.Constraint(self.flowsheet().config.time, doc="Prandtl number")
        def N_Pr_eqn(b, t):
            return b.N_Pr[t]*b.control_volume.properties_in[t].therm_cond_phase["Vap"] \
                   * b.control_volume.properties_in[t].mw == \
                   b.control_volume.properties_in[t].cp_mol_phase["Vap"] * \
                   b.control_volume.properties_in[t].visc_d_phase["Vap"]

        # Forced convection heat transfer coefficient for liquid only
        @self.Constraint(self.flowsheet().config.time, doc="forced convection heat transfer coefficient for liquid only")
        def hconv_eqn(b, t):
            return b.hconv[t] * b.diameter_in == 0.023 * b.N_Re[t]**0.8 * b.N_Pr[t]**0.4 * \
                   b.control_volume.properties_in[t].therm_cond_phase["Vap"]

    def set_initial_condition(self):
        if self.config.dynamic is True:
            self.control_volume.material_accumulation[:,:,:].value = 0
            self.control_volume.energy_accumulation[:,:].value = 0
            self.energy_accumulation_slag[:].value = 0
            self.energy_accumulation_metal[:].value = 0
            self.control_volume.material_accumulation[0,:,:].fix(0)
            self.control_volume.energy_accumulation[0,:].fix(0)
            self.energy_accumulation_slag[0].fix(0)
            self.energy_accumulation_metal[0].fix(0)

    def initialize(blk, state_args=None, outlvl=0, solver='ipopt', optarg={'tol': 1e-6}):
        '''
        Waterwall section initialization routine.

        Keyword Arguments:
            state_args : a dict of arguments to be passed to the property
                           package(s) for the control_volume of the model to
                           provide an initial state for initialization
                           (see documentation of the specific property package)
                           (default = None).
            outlvl : sets output level of initialisation routine

                     * 0 = no output (default)
                     * 1 = return solver state for each step in routine
                     * 2 = return solver state for each step in subroutines
                     * 3 = include solver output infomation (tee=True)

            optarg : solver options dictionary object (default={'tol': 1e-6})
            solver : str indicating whcih solver to use during
                     initialization (default = 'ipopt')

        Returns:
            None
        '''
        init_log = idaeslog.getInitLogger(blk.name, outlvl, tag="unit")
        solve_log = idaeslog.getSolveLogger(blk.name, outlvl, tag="unit")

        opt = SolverFactory(solver)
        opt.options = optarg

        flags = blk.control_volume.initialize(
            outlvl=outlvl+1,
            optarg=optarg,
            solver=solver,
            state_args=state_args
        )
        init_log.info_high("Initialization Step 1 Complete.")

        # Fix outlet enthalpy and pressure
        for t in blk.flowsheet().config.time:
            blk.control_volume.properties_out[t].enth_mol.fix(
                value(blk.control_volume.properties_in[t].enth_mol) +
                value(blk.heat_fireside[t])/
                value(blk.control_volume.properties_in[t].flow_mol)
            )
            blk.control_volume.properties_out[t].pressure.fix(
                value(blk.control_volume.properties_in[t].pressure) - 1.0
            )

        blk.heat_eqn.deactivate()
        blk.pressure_change_eqn.deactivate()

        with idaeslog.solver_log(solve_log, idaeslog.DEBUG) as slc:
            res = opt.solve(blk, tee=slc.tee)
        init_log.info_high(
                "Initialization Step 2 {}.".format(idaeslog.condition(res))
            )

        # Unfix outlet enthalpy and pressure
        for t in blk.flowsheet().config.time:
            blk.control_volume.properties_out[t].enth_mol.unfix()
            blk.control_volume.properties_out[t].pressure.unfix()
        blk.heat_eqn.activate()
        blk.pressure_change_eqn.activate()

        with idaeslog.solver_log(solve_log, idaeslog.DEBUG) as slc:
            res = opt.solve(blk, tee=slc.tee)
        init_log.info_high(
                "Initialization Step 3 {}.".format(idaeslog.condition(res))
            )

        blk.control_volume.release_state(flags, outlvl+1)
        init_log.info("Initialization Complete.")

    def calculate_scaling_factors(self):
        super().calculate_scaling_factors()
        for v in self.N_Re.values():
            if iscale.get_scaling_factor(v, warning=True) is None:
                iscale.set_scaling_factor(v, 1e-6)
        for t, c in self.Reynolds_number_eqn.items():
            s = iscale.get_scaling_factor(
                self.N_Re[t], default=1, warning=True)
            iscale.constraint_scaling_transform(c, s*1e5)
        for t, c in self.heat_flux_conv_eqn.items():
            s = iscale.get_scaling_factor(
                self.heat_flux_conv[t], default=1, warning=True)
            iscale.constraint_scaling_transform(c, s)
        for t, c in self.hconv_eqn.items():
            s = iscale.get_scaling_factor(
                self.hconv[t], default=1, warning=True)
            s *= iscale.get_scaling_factor(
                self.diameter_in, default=1, warning=True)
            iscale.constraint_scaling_transform(c, s)
        for t, c in self.pressure_change_eqn.items():
            s = iscale.get_scaling_factor(
                self.deltaP[t], default=1, warning=True)
            s *= iscale.get_scaling_factor(
                self.diameter_in, default=1, warning=True)
            iscale.constraint_scaling_transform(c, s)