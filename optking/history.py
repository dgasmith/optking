import math
import logging

import numpy as np
import qcelemental as qcel

from . import intcosMisc
from . import optparams as op
from .linearAlgebra import absMax, rms, signOfDouble
from .printTools import printMatString, printArrayString


class Step(object):
    def __init__(self, geom, E, forces, qcout=None):
        self.geom = geom.copy()  # Store as 2D object
        self.E = E
        self.forces = forces.copy()
        self.qcout = qcout
        self.projectedDE = None
        self.Dq = None
        self.followedUnitVector = None
        self.oneDgradient = None
        self.oneDhessian = None

    def record(self, projectedDE, Dq, followedUnitVector, oneDgradient, oneDhessian):
        self.projectedDE = projectedDE
        self.Dq = Dq.copy()
        self.followedUnitVector = followedUnitVector.copy()
        self.oneDgradient = oneDgradient
        self.oneDhessian = oneDhessian

    def __str__(self):
        s = "Step Info\n"
        s += "Geometry     = \n"
        s += printMatString(self.geom)
        s += "Energy       = %15.10f\n" % self.E
        s += "forces       = "
        s += printArrayString(self.forces)
        s += "Projected DE = %15.10f\n" % self.projectedDE
        s += "Dq           = "
        s += printArrayString(self.Dq)
        s += "followedUnitVector       = "
        s += printArrayString(self.followedUnitVector)
        s += "oneDgradient = %15.10f\n" % self.oneDgradient
        s += "oneDhessian  = %15.10f\n" % self.oneDhessian
        return s


class History(object):
    stepsSinceLastHessian = 0
    consecutiveBacksteps = 0
    nuclear_repulsion_energy = 0

    def __init__(self):
        self.steps = []
        History.stepsSinceLastHessian = 0

    def __str__(self):
        s = "History of length %d\n" % len(self)
        for i, step in enumerate(self.steps):
            s += "Step %d\n" % (i + 1)
            s += step.__str__()
        return s

    def __len__(self):
        return len(self.steps)

    def __getitem__(self, index):
        return self.steps[index]

    def __setitem__(self, index, item):
        self.steps[index] = item

    def __delitem__(self, index):
        del self.steps[index]

    # Add new step.  We will store geometry as 1D in history.
    def append(self, geom, E, forces, qcout):
        s = Step(geom, E, forces, qcout)
        self.steps.append(s)
        History.stepsSinceLastHessian += 1

    # Fill in details of new step.
    def appendRecord(self, projectedDE, Dq, followedUnitVector, oneDgradient,
                     oneDhessian):
        self.steps[-1].record(projectedDE, Dq, followedUnitVector, oneDgradient,
                              oneDhessian)

    def trajectory(self, Zs):
        t = []
        Zstring = [qcel.periodictable.to_E(i) for i in Zs]
        for iS, S in enumerate(self.steps):
            t.append((S.E, list(Zstring), S.geom.copy()))
        return t

    # Summarize key quantities and return steps or string
    def summary(self, printoption=False):
        opt_summary = ''
        steps = []

        for i, step in enumerate(self.steps):
            if i == 0:
                DE = step.E
            else:
                DE = step.E - self.steps[i - 1].E

            max_force = absMax(step.forces)
            rms_force = rms(step.forces)

            # For the summary Dq, we do not want to +2*pi for example for the angles,
            # so we read old Dq used during step.
            try:
                max_disp = absMax(step.Dq)
                rms_disp = rms(step.Dq)
            except:
                max_disp = -99.0
                rms_disp = -99.0

            steps.append({
                'Energy': step.E,
                'DE': DE,
                'max_force': max_force,
                'max_disp': max_disp,
                'rms_disp': rms_disp,
                'raw_output': step.qcout,
            })

            opt_summary += ("\t  %4d %20.12lf  %18.12lf    %12.8lf    %12.8lf    %12.8lf    %12.8lf  ~\n" % (
                (i + 1), self.steps[i].E, DE, max_force, rms_force, max_disp, rms_disp))

        opt_summary += ("\t" + "-" * 112 + "\n\n")

        if printoption:
            return opt_summary
        else:
            return steps

    # Report on performance of last step
    # Eventually might have this function return False to reject a step
    def currentStepReport(self):
        logger = logging.getLogger(__name__)

        opt_step_report = "\n\tCurrent energy: %20.10lf\n" % self.steps[-1].E
        if len(self.steps) < 2:
            return True

        energyChange = self.steps[-1].E - self.steps[-2].E
        projectedChange = self.steps[-2].projectedDE

        opt_step_report += "\tEnergy change for the previous step:\n"
        opt_step_report += "\t\tActual       : %20.10lf\n" % energyChange
        if projectedChange is not None:
            opt_step_report += "\t\tProjected    : %20.10lf\n" % projectedChange

        logger.info("\tCurrent Step Report \n %s" % opt_step_report)

        if projectedChange is None:
            return True # no previous projection; could be first step?

        Energy_ratio = energyChange / projectedChange

        if op.Params.print_lvl >= 1:
            logger.info("\tEnergy ratio = %10.5lf" % Energy_ratio)

        if op.Params.opt_type == 'MIN':
            # Predicted up. Actual down.  OK.  Do nothing.
            if projectedChange > 0 and Energy_ratio < 0.0:
                return True
            # Actual step is  up.
            elif energyChange > 0:
                logger.warning("\tEnergy has increased in a minimization.")
                op.Params.decreaseTrustRadius()
                return False
            # Predicted down.  Actual down.
            elif Energy_ratio < 0.25:
                op.Params.decreaseTrustRadius()
            elif Energy_ratio > 0.75:
                op.Params.increaseTrustRadius()

        return True

    # Keep only most recent step
    def resetToMostRecent(self):
        self.steps = self.steps[-1:]
        History.stepsSinceLastHessian = 0
        consecutiveBacksteps = 0
        nuclear_repulsion_energy = 0
        # The step included is not taken in an IRC.
        self.steps[0].projectedDE = None
        return

    # Use History to update Hessian
    def hessianUpdate(self, H, intcos):
        logger = logging.getLogger(__name__)
        if op.Params.hess_update == 'NONE' or len(self.steps) < 2:
            return

        logger.info("\tPerforming %s update." % op.Params.hess_update)
        Nintco = len(intcos)  # working dimension

        f = np.zeros(Nintco, float)
        # x = np.zeros(self.steps[-1].geom.shape,float)
        q = np.zeros(Nintco, float)

        currentStep = self.steps[-1]
        f[:] = currentStep.forces
        # x[:] = currentStep.geom
        x = currentStep.geom
        q[:] = intcosMisc.qValues(intcos, x)

        # Fix configuration of torsions and out-of-plane angles,
        # so that Dq's are reasonable
        intcosMisc.updateDihedralOrientations(intcos, x)

        dq = np.zeros(Nintco, float)
        dg = np.zeros(Nintco, float)
        q_old = np.zeros(Nintco, float)

        # Don't go further back than the last Hessian calculation
        numToUse = min(op.Params.hess_update_use_last,
                       len(self.steps) - 1, History.stepsSinceLastHessian)
        logger.info("\tUsing %d previous steps for update." % numToUse)

        # Make list of old geometries to update with.
        # Check each one to see if it is too close (so stable denominators).
        use_steps = []
        iStep = len(self.steps)-2 # just in case called with only 1 pt.
        while iStep > -1 and len(use_steps) < numToUse:
            oldStep = self.steps[iStep]
            f_old = oldStep.forces
            x_old = oldStep.geom
            q_old[:] = intcosMisc.qValues(intcos, x_old)
            dq[:] = q - q_old
            dg[:] = f_old - f  # gradients -- not forces!
            gq = np.dot(dq, dg)
            qq = np.dot(dq, dq)
            max_change = absMax(dq)

            # If there is only one left, take it no matter what.
            if len(use_steps) == 0 and iStep == 0:
                use_steps.append(iStep)
            elif (math.fabs(gq) < op.Params.hess_update_den_tol or
                math.fabs(qq) < op.Params.hess_update_den_tol):
                logger.warning("\tDenominators (dg)(dq) or (dq)(dq) are very small.")
                logger.warning("\tSkipping Hessian update for step %d." % (iStep + 1))
                pass
            elif max_change > op.Params.hess_update_dq_tol:
                logger.warning("\tChange in internal coordinate of %5.2e exceeds limit of %5.2e."
                               % (max_change, op.Params.hess_update_dq_tol))
                logger.warning("\tSkipping Hessian update for step %d." % (iStep + 1))
                pass
            else:
                use_steps.append(iStep)
            iStep -= 1

        hessian_steps = ("\tSteps to be used in Hessian update: ")
        for i in use_steps:
            hessian_steps += " %d" % (i + 1)
        hessian_steps += "\n"

        logger.info(hessian_steps)

        H_new = np.zeros(H.shape, float)
        for i_step in use_steps:
            oldStep = self.steps[i_step]

            f_old = oldStep.forces
            x_old = oldStep.geom
            q_old[:] = intcosMisc.qValues(intcos, x_old)
            dq[:] = q - q_old
            dg[:] = f_old - f  # gradients -- not forces!
            gq = np.dot(dq, dg)
            qq = np.dot(dq, dq)

            # See  J. M. Bofill, J. Comp. Chem., Vol. 15, pages 1-11 (1994)
            #  and Helgaker, JCP 2002 for formula.
            if op.Params.hess_update == 'BFGS':
                for i in range(Nintco):
                    for j in range(Nintco):
                        H_new[i, j] = H[i, j] + dg[i] * dg[j] / gq

                Hdq = np.dot(H, dq)
                dqHdq = np.dot(dq, Hdq)

                for i in range(Nintco):
                    for j in range(Nintco):
                        H_new[i, j] -= Hdq[i] * Hdq[j] / dqHdq

            elif op.Params.hess_update == 'MS':
                Z = -1.0 * np.dot(H, dq) + dg
                qz = np.dot(dq, Z)

                for i in range(Nintco):
                    for j in range(Nintco):
                        H_new[i, j] = H[i, j] + Z[i] * Z[j] / qz

            elif op.Params.hess_update == 'POWELL':
                Z = -1.0 * np.dot(H, dq) + dg
                qz = np.dot(dq, Z)

                for i in range(Nintco):
                    for j in range(Nintco):
                        H_new[i, j] = H[i, j] - qz / (qq * qq) * dq[i] * dq[j] + (
                            Z[i] * dq[j] + dq[i] * Z[j]) / qq

            elif op.Params.hess_update == 'BOFILL':
                # Bofill = (1-phi) * MS + phi * Powell
                Z = -1.0 * np.dot(H, dq) + dg
                qz = np.dot(dq, Z)
                zz = np.dot(Z, Z)

                phi = 1.0 - qz * qz / (qq * zz)
                if phi < 0.0:
                    phi = 0.0
                elif phi > 1.0:
                    phi = 1.0

                for i in range(Nintco):  # (1-phi)*MS
                    for j in range(Nintco):
                        H_new[i, j] = H[i, j] + (1.0 - phi) * Z[i] * Z[j] / qz

                for i in range(Nintco):  # (phi * Powell)
                    for j in range(Nintco):
                        H_new[i, j] += phi * (-1.0 * qz / (qq * qq) * dq[i] * dq[j] +
                                              (Z[i] * dq[j] + dq[i] * Z[j]) / qq)

            if op.Params.hess_update_limit:  # limit changes in H
                # Changes to the Hessian from the update scheme are limited to the larger of
                # (hess_update_limit_scale)*(the previous value) and hess_update_limit_max.
                max_limit = op.Params.hess_update_limit_max
                scale_limit = op.Params.hess_update_limit_scale

                # Compute change in Hessian
                H_new[:, :] = H_new - H

                for i in range(Nintco):
                    for j in range(Nintco):
                        val = math.fabs(scale_limit * H[i, j])
                        maximum = max(val, max_limit)

                        if math.fabs(H_new[i, j]) < maximum:
                            H[i, j] += H_new[i, j]
                        else:  # limit change to max
                            H[i, j] += maximum * signOfDouble(H_new[i, j])

            else:  # only copy H_new into H
                H[:, :] = H_new

            H_new[:, :] = 0  # zero for next step
            # end loop over old geometries

        if op.Params.print_lvl >= 2:
            logger.info("\tUpdated Hessian (in au) \n %s" % printMatString(H))
        return


def summaryString():
    output_string = """\n\t==> Optimization Summary <==\n
    \n\tMeasures of convergence in internal coordinates in au. (Any backward steps not shown.)
    \n\t---------------------------------------------------------------------------------------------------------------  ~
    \n\t Step         Total Energy             Delta E       MAX Force       RMS Force        MAX Disp        RMS Disp   ~
    \n\t---------------------------------------------------------------------------------------------------------------  ~
    \n"""
    output_string += oHistory.summary(printoption=True)

    return output_string


oHistory = History()
