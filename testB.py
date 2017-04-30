# Test the analytic B matrix (dq/dx) via finite differences
# The 5-point formula should be good to DISP_SIZE^4 -
#  a few unfortunates will be slightly worse
import numpy as np
import intcosMisc
from printTools import printMat
import optParams as op
from math import fabs

def testB(intcos, geom):
    Natom = len(geom)
    Nintco = len(intcos)
    DISP_SIZE = 0.01
    MAX_ERROR = 50*DISP_SIZE*DISP_SIZE*DISP_SIZE*DISP_SIZE

    print "\n\tTesting B-matrix numerically..."

    B_analytic = intcosMisc.Bmat(intcos, geom)

    if op.Params.print_lvl >= 3:
        print "Analytic B matrix in au"
        printMat(B_analytic)

    B_fd = np.zeros( (Nintco, 3*Natom), float)

    intcosMisc.updateDihedralOrientations(intcos, geom)
    intcosMisc.fixBendAxes(intcos, geom)

    coord = geom.copy()

    for atom in range(Natom):
        for xyz in range(3):
            coord[atom,xyz] -= DISP_SIZE
            q_m   = intcosMisc.qValues(intcos, coord)
            coord[atom,xyz] -= DISP_SIZE
            q_m2  = intcosMisc.qValues(intcos, coord)
            coord[atom,xyz] += 3*DISP_SIZE
            q_p  = intcosMisc.qValues(intcos, coord)
            coord[atom,xyz] += DISP_SIZE
            q_p2 = intcosMisc.qValues(intcos, coord)
            coord[atom,xyz] -= 2*DISP_SIZE # restore to original
            for i in range(Nintco):
                B_fd[i,3*atom+xyz] = (q_m2[i]-8*q_m[i]+8*q_p[i]-q_p2[i]) / (12.0*DISP_SIZE)

    if op.Params.print_lvl >= 3:
        print "Numerical B matrix in au, DISP_SIZE = %lf" % DISP_SIZE
        printMat(B_fd)

    intcosMisc.unfixBendAxes(intcos)

    max_error = -1.0
    max_error_intco = -1
    for i in range(Nintco):
        for j in range(3*Natom):
            if fabs(B_analytic[i,j] - B_fd[i,j]) > max_error:
                max_error = fabs(B_analytic[i][j] - B_fd[i][j])
                max_error_intco = i
  
    print "\t\tMaximum difference is %.1e for internal coordinate %d." % (max_error, max_error_intco+1)
    print "\t\tThis coordinate is ", intcos[max_error_intco]

    if max_error > MAX_ERROR:
       print "\tB-matrix could be in error. However, numerical tests may fail for"
       print "\ttorsions at 180 degrees, and slightly for linear bond angles. This is OK."
       return False
    else:
       print "\t...Passed."
       return True
  

# Test the analytic derivative B matrix (d2q/dx2) via finite differences
# The 5-point formula should be good to DISP_SIZE^4 -
#  a few unfortunates will be slightly worse

def testDerivativeB(intcos, geom_in):
    Natom = len(geom_in)
    Nintco = len(intcos)
    DISP_SIZE = 0.01
    MAX_ERROR = 10*DISP_SIZE*DISP_SIZE*DISP_SIZE*DISP_SIZE;

    dq2dx2_fd       = np.zeros( (3*Natom, 3*Natom), float)
    dq2dx2_analytic = np.zeros( (3*Natom, 3*Natom), float)
    coord           = np.copy(geom_in)

    print "\n\tTesting Derivative B-matrix numerically..."

    warn = False
    for i in range(Nintco):  # test one intco at a time

        print "\t\tTesting internal coordinate %d : " % (i+1) 

        dq2dx2_analytic.fill(0)
        intcos[i].Dq2Dx2(coord, dq2dx2_analytic)

        if op.Params.print_lvl >= 3:
            print  "Analytic B' (Dq2Dx2) matrix in au"
            printMat(dq2dx2_analytic)

        # compute B' matrix from B matrices
        for atom_a in range(Natom):
            for xyz_a in range(3):

                coord[atom_a,xyz_a] += DISP_SIZE
                B_p  = intcosMisc.Bmat(intcos, coord)

                coord[atom_a,xyz_a] += DISP_SIZE
                B_p2 = intcosMisc.Bmat(intcos, coord)

                coord[atom_a,xyz_a] -= 3.0*DISP_SIZE
                B_m  = intcosMisc.Bmat(intcos, coord)

                coord[atom_a,xyz_a] -= DISP_SIZE
                B_m2 = intcosMisc.Bmat(intcos, coord)

                coord[atom_a,xyz_a] += 2*DISP_SIZE # restore coord to orig
    
                for atom_b in range(Natom):
                    for xyz_b in range(3):
                        dq2dx2_fd[3*atom_a+xyz_a,3*atom_b+xyz_b] = \
                        (B_m2[i,3*atom_b+xyz_b] - 8*B_m[i,3*atom_b+xyz_b] + \
                         8*B_p[i,3*atom_b+xyz_b] - B_p2[i][3*atom_b+xyz_b]) / (12.0*DISP_SIZE)


        if op.Params.print_lvl >= 3:
            print "\nNumerical B' (Dq2Dx2) matrix in au, DISP_SIZE = %f" % DISP_SIZE
            printMat(dq2dx2_fd)

        max_error = -1.0;
        max_error_xyz = (-1,-1)
        for I in range(3*Natom):
            for J in range(3*Natom):
                if fabs(dq2dx2_analytic[I,J] - dq2dx2_fd[I,J]) > max_error:
                    max_error = fabs(dq2dx2_analytic[I][J] - dq2dx2_fd[I][J])
                    max_error_xyz = (I,J)

        print "\t\tMax. difference is %.1e; 2nd derivative wrt %d and %d." % (max_error,I+1,J+1)

        if max_error > MAX_ERROR:
            warn = True

    if warn:
        print "\tSome values did not agree.  However, numerical tests may fail for"
        print "\ttorsions at 180 degrees and linear bond angles. This is OK."
        print "\tIf discontinuities are interfering with a geometry optimization,"
        print "\ttry restarting your optimization at an updated geometry, and/or"
        print "\tremove angular coordinates that are fixed by symmetry."

    return

