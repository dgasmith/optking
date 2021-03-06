import numpy as np
import logging

from . import intcosMisc
from .exceptions import AlgError, OptError
from . import optparams as op
from .linearAlgebra import absMax, rms, symmMatInv

# dq : displacements in internal coordinates to be performed.
#      On exit, overridden to actual displacements performed.
# fq : internal coordinate forces (used for printing).
# atom_offset : increment to atom #'s in the fragment (used for printing)
# ensure_convergence :
#   Reduce step size as necessary until back-transformation converges.


def displace(intcos, geom, dq, fq=None, atom_offset=0, ensure_convergence=False):
    """ Converts internal coordinate step into the new cartesian geometry

    Parameters
    ----------
    intcos : list of Stre, Bend, Tors, or Oofp
    geom : ndarray
        (nat, 3) cartesian geometry
        overriden to new geometry after step
    dq : ndarray
        step (displacement) in internal coordiantes
        overriden to actual displacements performed
    fq : ndarray
        forces in internal coordinates


    """
    logger = logging.getLogger(__name__)
    if not len(intcos) or not len(geom) or not len(dq):
        dq[:] = 0
        return

    Nint = len(intcos)

    intcosMisc.updateDihedralOrientations(intcos, geom)
    geom_orig = np.copy(geom)
    dq_orig = np.copy(dq)
    intcosMisc.unfixBendAxes(intcos)
    q_orig = intcosMisc.qValues(intcos, geom_orig)

    best_geom = np.zeros(geom_orig.shape, float)

    # Do your best to backtransform all internal coordinate displacments.
    logger.info("\tBeginnning displacement in cartesian coordinates...")

    if ensure_convergence:
        conv = False
        cnt = -1

        while not conv:
            cnt = cnt + 1
            if cnt > 0:
                logger.info("\tReducing step-size by a factor of %d." % (2 * cnt))
                dq[:] = dq_orig / (2.0 * cnt)

            intcosMisc.fixBendAxes(intcos, geom)
            conv = stepIter(intcos, geom, dq)
            intcosMisc.unfixBendAxes(intcos)

            if not conv:
                if cnt == 5:
                    logger.warning(
                        "\tUnable to back-transform even 1/10th of the desired step rigorously."
                        + "\tContinuing with best (small) step")
                    break
                else:
                    geom[:] = geom_orig  # put original geometry back for next try at smaller step.

        if conv and cnt > 0:  # We were able to take a modest step.  Try to complete it.
            logger.info(
                "\tAble to take a small step; trying another partial back-transformations.\n")

            for j in range(1, 2 * cnt):
                logger.info("\tMini-step %d of %d.\n", (j + 1, 2 * cnt))
                dq[:] = dq_orig / (2 * cnt)

                best_geom[:] = geom

                intcosMisc.fixBendAxes(intcos, geom)
                conv = stepIter(intcos, geom, dq)
                intcosMisc.unfixBendAxes(intcos)

                if not conv:
                    logger.warning(
                        "\tCouldn't converge this mini-step; quitting with previous geometry.\n")
                    geom[:] = best_geom
                    break

    else:  # try to back-transform, but continue even if desired dq is not achieved
        intcosMisc.fixBendAxes(intcos, geom)
        stepIter(intcos, geom, dq)
        intcosMisc.unfixBendAxes(intcos)

    # Fix drift/error in any frozen coordinates
    if any(intco.frozen for intco in intcos):

        # Set dq for unfrozen intcos to zero.
        dq_adjust_frozen = q_orig - intcosMisc.qValues(intcos, geom)

        for i, intco in enumerate(intcos):
            if not intco.frozen:
                dq_adjust_frozen[i] = 0

        success_of_back_trans = (
                "\n\tBack-transformation to cartesian coordinates to adjust frozen coordinates: \n")

        intcosMisc.fixBendAxes(intcos, geom)
        check = stepIter(
            intcos,
            geom,
            dq_adjust_frozen,
            bt_dx_conv=1.0e-12,
            bt_dx_rms_change_conv=1.0e-12,
            bt_max_iter=100)
        intcosMisc.unfixBendAxes(intcos)

        if check:
            success_of_back_trans += ("\tsuccessful.\n")
            logger.info(success_of_back_trans)
        else:
            success_of_back_trans += ("\tunsuccessful, but continuing.\n")
            logger.warning(success_of_back_trans)

    # Make sure final Dq is actual change
    q_final = intcosMisc.qValues(intcos, geom)
    dq[:] = q_final - q_orig

    if op.Params.print_lvl >= 1:
        back_trans_report = ("\tReport of back-transformation: (au)\n")
        back_trans_report += ("\n\t  int       q_target          Error\n")
        back_trans_report += ("\t-----------------------------------\n")
        q_target = q_orig + dq_orig
        for i in range(Nint):
            back_trans_report += ("\t%5d%15.10lf%15.10lf\n"
                                  % (i + 1, q_target[i], (q_final - q_target)[i]))
        back_trans_report += ("\t-----------------------------------\n")
        logger.debug(back_trans_report)

    # Set dq to final, total displacement ACHIEVED
    qShow_final = intcosMisc.qShowValues(intcos, geom)
    qShow_orig = intcosMisc.qShowValues(intcos, geom_orig)
    dqShow = qShow_final - qShow_orig

    coordinate_change_report = (
        "\n\n\t       --- Internal Coordinate Step in ANG or DEG, aJ/ANG or AJ/DEG ---\n")
    coordinate_change_report += (
        "\t-----------------------------------------------------------------------------\n")
    coordinate_change_report += (
        "\t         Coordinate      Previous         Change          New \n")
    coordinate_change_report += (
        "\t         ----------      --------        ------        ------\n")

    if type(fq) == type(None):
        for i, intco in enumerate(intcos):
            coordinate_change_report += ("\t%19s%14.5f%14.5f%14.5f\n"
                                         % (intco, qShow_orig[i], dqShow[i], qShow_final[i]))
    else:
        for i, intco in enumerate(intcos):
            coordinate_change_report += ("\t%19s%14.5f%14.5f%14.5f%14.5f\n"
                                         % (intco, qShow_orig[i], fq[i], dqShow[i], qShow_final[i]))
    coordinate_change_report += (
        "\t-----------------------------------------------------------------------------\n")

    logger.info(coordinate_change_report)


def stepIter(intcos, geom, dq,
             bt_dx_conv=None, bt_dx_rms_change_conv=None, bt_max_iter=None):
    logger = logging.getLogger(__name__)
    dx_rms_last = -1
    if bt_dx_conv is None:
        bt_dx_conv = op.Params.bt_dx_conv
    if bt_dx_rms_change_conv is None:
        bt_dx_rms_change_conv = op.Params.bt_dx_rms_change_conv
    if bt_max_iter is None:
        bt_max_iter = op.Params.bt_max_iter

    print_lvl = op.Params.print_lvl

    q_orig = intcosMisc.qValues(intcos, geom)
    q_target = q_orig + dq

    if print_lvl > 1:
        step_iter_str = ("\n\n\t---------------------------------------------------\n")
        step_iter_str += ("\t Iter        RMS(dx)        Max(dx)        RMS(dq) \n")
        step_iter_str += ("\t---------------------------------------------------\n")

    new_geom = np.copy(geom)  # cart geometry to start each iter
    best_geom = np.zeros(new_geom.shape, float)

    bt_iter_continue = True
    bt_converged = False
    bt_iter_cnt = 0

    while bt_iter_continue:

        dq_rms = rms(dq)
        dx_rms, dx_max = oneStep(intcos, geom, dq, print_lvl > 2)

        # Met convergence thresholds
        if dx_rms < bt_dx_conv and dx_max < bt_dx_conv:
            bt_converged = True
            bt_iter_continue = False
        # No further progress toward convergence.
        elif (np.absolute(dx_rms - dx_rms_last) < bt_dx_rms_change_conv
              or bt_iter_cnt >= bt_max_iter or dx_rms > 100.0):
            bt_converged = False
            bt_iter_continue = False

        dx_rms_last = dx_rms

        new_q = intcosMisc.qValues(intcos, geom)
        dq[:] = q_target - new_q
        del new_q

        if bt_iter_cnt == 0 or dq_rms < best_dq_rms:  # short circuit evaluation
            best_geom[:] = geom
            best_dq_rms = dq_rms

        if print_lvl > 1:
            step_iter_str += ("\t%5d %14.1e %14.1e %14.1e\n"
                              % (bt_iter_cnt + 1, dx_rms, dx_max, dq_rms))
        bt_iter_cnt += 1

    if print_lvl > 1:
        step_iter_str += ("\t---------------------------------------------------\n")
        logger.info(step_iter_str)

    if bt_converged:
        logger.info("\tSuccessfully converged to displaced geometry.")
    else:
        logger.warning("\tUnable to completely converge to displaced geometry.")

    if dq_rms > best_dq_rms:
        logger.warning("\tPrevious geometry is closer to target in internal coordinates,"
                       + " so using that one.\n")
        logger.warning("\tBest geometry has RMS(Delta(q)) = %8.2e\n" % best_dq_rms)
        geom[:] = best_geom

    if op.Params.opt_type == "IRC" and not bt_converged:
        raise OptError(
            "Could not take constrained step in an IRC computation.")

    return bt_converged


# Convert dq to dx.  Geometry is updated.
# B dx = dq
# B dx = (B Bt)(B Bt)^-1 dq
# B (dx) = B * [Bt (B Bt)^-1 dq]
#   dx = Bt (B Bt)^-1 dq
#   dx = Bt G^-1 dq, where G = B B^t.
def oneStep(intcos, geom, dq, printDetails=False):
    """ Convert dq to dx.  Geometry is updated

    Parameters
    ----------
    intcos : list of Stre, Bend, Tors, or Oofp
    geom : ndarray
        cartesian geometry updated to new geometry
    dq : displacement in internal coordinates

    Returns
    -------
    float :
        rms of cartesian displacement
    float :
        absolute maximum of cartesian displacement
    """
    B = intcosMisc.Bmat(intcos, geom)
    G = np.dot(B, B.T)
    Ginv = symmMatInv(G, redundant=True)
    tmp_v_Nint = np.dot(Ginv, dq)
    # dx = np.zeros(geom.shape[0] * geom.shape[1], float)  # dx is 1D here

    dx = np.dot(B.T, tmp_v_Nint)
    if printDetails:
        qOld = intcosMisc.qValues(intcos, geom)
    geom += dx.reshape(geom.shape)

    if printDetails:
        # qNew = intcosMisc.qValues(intcos, geom) ## variable not used
        dq_achieved = intcosMisc.qValues(intcos, geom) - qOld
        # printArray(dq_achieved)
        displacement_str = ("\t      Report of Single-step\n")
        displacement_str += ("\t  int       dq_achieved        dq_error\n")
        for i in range(len(intcos)):
            displacement_str += ("\t%5d%15.10lf%15.10lf\n"
                                 % (i + 1, dq_achieved[i], dq_achieved[i] - dq[i]))
    dx_rms = rms(dx)
    dx_max = absMax(dx)
    del B, G, Ginv, tmp_v_Nint, dx
    return dx_rms, dx_max
