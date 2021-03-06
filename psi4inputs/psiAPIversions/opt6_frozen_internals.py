#! Various constrained energy minimizations of HOOH with cc-pvdz RHF
#! Internal-coordinate constraints in internal-coordinate optimizations.

import psi4
import runpsi4API

OH_frozen_stre_rhf       = -150.781130357 #TEST
OOH_frozen_bend_rhf      = -150.786372411 #TEST
HOOH_frozen_dihedral_rhf = -150.786766848 #TEST
#
#
## Constrained minimization with O-H bonds frozen.
#hooh = psi4.geometry("""
#  H
#  O 1 0.90
#  O 2 1.40 1 100.0 
#  H 3 0.90 2 100.0 1 115.0
#""")
#
#psi4.set_options({
#  'diis': 'false',
#  'basis': 'cc-PVDZ',
#  'g_convergence': 'gau_verytight',
#  'scf_type': 'pk', 
#})
#
#frozen_stre = ("""
#    1  2
#    3  4
#""")
#
#psi4.set_module_options('OPTKING', {'frozen_distance': frozen_stre})
#Psi4Opt.calcName = 'hf'
#thisenergy = Psi4Opt.Psi4Opt()
#psi4.compare_values(OH_frozen_stre_rhf, thisenergy, 7, 
#                    "Int. Coord. RHF opt of HOOH with O-H frozen, energy")  #TEST

#Constrained minimization with O-O-H angles frozen.
hooh = psi4.geometry("""
  H
  O 1 0.90
  O 2 1.40 1 100.0
  H 3 0.90 2 100.0 1 115.0
  no_com
  no_reorient
  symmetry c1
""")


psi4options = {
  'diis': 'false',
  'basis': 'cc-PVDZ',
  'g_convergence': 'gau_verytight',
  'scf_type': 'pk'
}

frozen_angles = ("""
    1 2 3
    2 3 4
""")

psi4.set_options(psi4options)

psi4.set_module_options('OPTKING', {'frozen_distance': '', 'frozen_bend': frozen_angles}) 
thisenergy, nucenergy = runpsi4API.Psi4Opt('hf', psi4options)
psi4.compare_values(OOH_frozen_bend_rhf, thisenergy, 7,
                    "Int. Coord. RHF opt of HOOH with O-O-H frozen, energy") #TEST

# Constrained minimization with H-O-O-H dihedral frozen.
#hooh = psi4.geometry("""
#  H
#  O 1 0.90
#  O 2 1.40 1 100.0 
#  H 3 0.90 2 100.0 1 115.0
#  no_com
#  no_reorient
#  symmetry c1
#""")
#
#frozen_tors = ("1 2 3 4")
#
#psi4options = {
#  'diis': 'false',
#  'basis': 'cc-PVDZ',
#  'g_convergence': 'gau_verytight',
#  'scf_type': 'pk'
#}
#
#psi4.set_module_options('OPTKING', {'frozen_distance': '', 'frozen_bend': '',
#                        'frozen_dihedral': frozen_tors}) 
#thisenergy, nucenergy = runpsi4API.Psi4Opt('hf', psi4options)
#psi4.compare_values(HOOH_frozen_dihedral_rhf, thisenergy, 7, 
#                    "Int. Coord. RHF opt of HOOH with H-O-O-H frozen, energy") #TEST
#
