from printTools import printMat, printArray, print_opt
import numpy as np
from math import sqrt
import bend
import oofp
import tors
from linearAlgebra import symmMatInv
import optParams as op

# Simple operations on internal :148
#coordinate sets.  For example,
# return values, Bmatrix or fix orientation.

# q    -> qValues
# DqDx -> Bmat
def qValues(intcos, geom):
    q  = np.zeros( (len(intcos)), float)
    for i, intco in enumerate(intcos):
        q[i] = intco.q(geom)
    return q

def qShowValues(intcos, geom):
    q  = np.zeros( (len(intcos)), float)
    for i, intco in enumerate(intcos):
        q[i] = intco.qShow(geom)
    return q

def updateDihedralOrientations(intcos, geom):
    for intco in intcos:
        if isinstance(intco, tors.TORS) or isinstance(intco, oofp.OOFP):
            intco.updateOrientation(geom)
    return

def fixBendAxes(intcos, geom):
    for intco in intcos:
        if isinstance(intco, bend.BEND):
            intco.fixBendAxes(geom)
    return

def unfixBendAxes(intcos):
    for intco in intcos:
        if isinstance(intco, bend.BEND):
            intco.unfixBendAxes()
    return

def Bmat(intcos, geom, masses=None):
    Nint = len(intcos)
    Ncart = geom.size

    B = np.zeros( (Nint,Ncart), float)
    for i,intco in enumerate(intcos):
        intco.DqDx(geom, B[i])

    if masses is not None:
        print_opt("mass weighting B matrix\n")
        for i in range(len(intcos)):
            for a in range(len(geom)):
                for xyz in range(3):
                    B[i, 3*a + xyz] /= sqrt(masses[a]);

    return B

def Gmat(intcos, geom, masses=None):
    B = Bmat(intcos, geom, masses)

    """
    if masses:
        for i in range(len(intcos)):
            for a in range(len(geom)):
                for xyz in range(3):
                    B[i][3*a+xyz] /= sqrt(masses[a]);
    """

    return np.dot(B, B.T)
        
# Compute forces in internal coordinates in au, f_q = G_inv B u f_x
# if u is unit matrix, f_q = (BB^T)^(-1) * B f_x
def qForces(intcos, geom, gradient_x):
    if len(intcos) == 0 or len(geom) == 0: return np.zeros( (0), float)
    B = Bmat(intcos, geom)
    fx = -1.0 * gradient_x     # gradient -> forces
    temp_arr = np.dot(B,fx.T)
    del fx

    G    = np.dot(B, B.T)  
    del B
    Ginv = symmMatInv(G,redundant=True)
    del G

    fq = np.dot(Ginv,temp_arr.T)
    return fq

# Prints them, but does not recompute them.
def qShowForces(intcos, forces):
    qaJ = np.copy(forces)
    for i, intco in enumerate(intcos):
        qaJ[i] *= intco.fShowFactor
    return qaJ

def constraint_matrix(intcos):
    if not any( [coord.frozen for coord in intcos ]):
        return None
    C = np.zeros((len(intcos),len(intcos)), float)
    for i,coord in enumerate(intcos):
        if coord.frozen:
            C[i,i] = 1.0
    return C

# Project redundancies and constraints out of forces and Hessian.
def projectRedundanciesAndConstraints(intcos, geom, fq, H):
    dim = len(intcos)

    # compute projection matrix = G G^-1
    G = Gmat(intcos, geom)
    G_inv = symmMatInv(G, redundant=True)
    Pprime = np.dot(G, G_inv) 
    if op.Params.print_lvl >= 3:
        print_opt("\tProjection matrix for redundancies.\n")
        printMat(Pprime)

    # Add constraints to projection matrix
    C = constraint_matrix(intcos)

    if C is not None:
        print_opt("Adding constraints for projection.\n")
        printMat(C)
        P= np.zeros((len(intcos), len(intcos)), float)
        #print_opt(np.dot(C, np.dot(Pprime, C)))
        CPC = np.zeros((len(intcos), len(intcos)), float) 
        CPC[:,:] = np.dot(C, np.dot(Pprime, C))
        CPC = symmMatInv(CPC, redundant = True)  
        P[:,:] = Pprime - np.dot(Pprime, np.dot(C, np.dot(CPC, np.dot(C, Pprime))))
        # Project redundancies out of forces.
        # fq~ = P fq
        fq[:] = np.dot(P, fq.T)

        if op.Params.print_lvl >= 3:
            print_opt("\tInternal forces in au, after projection of redundancies and constraints.\n")
            printArray(fq)
        # Project redundancies out of Hessian matrix.
        # Peng, Ayala, Schlegel, JCC 1996 give H -> PHP + 1000(1-P)
        # The second term appears unnecessary and sometimes messes up Hessian updating.
        tempMat = np.dot(H, P)
        H[:,:] = np.dot(P, tempMat)
        #for i in range(dim)
        #    H[i,i] += 1000 * (1.0 - P[i,i])
        #for i in range(dim)
        #    for j in range(i):
        #        H[j,i] = H[i,j] = H[i,j] + 1000 * (1.0 - P[i,j])
        if op.Params.print_lvl >= 3:
            print_opt("Projected (PHP) Hessian matrix\n")
            printMat(H)

def applyFixedForces(Molsys, fq, H, stepNumber):
    x = Molsys.geom
    for iF,F in enumerate(Molsys._fragments):
        for i, intco in enumerate(F.intcos):
            if intco.fixed:
              location = Molsys.frag_1st_intco(iF) + i
              val   = intco.q(x)
              eqVal = intco.fixedEqVal

              # Increase force constant by 5% of initial value per iteration
              k = (1 + 0.05 * stepNumber) * op.Params.fixed_coord_force_constant
              force = k * (eqVal - val)
              H[location][location] = k

              print_opt("\n\tAdding user-defined constraint: Fragment %d; Coordinate %d:\n" % (iF+1, i+1))
              print_opt("\t\tValue = %12.6f; Fixed value    = %12.6f" % (val, eqVal))
              print_opt("\t\tForce = %12.6f; Force constant = %12.6f" % (force, k))
              fq[location] = force

              # Delete coupling between this coordinate and others.
              print_opt("\t\tRemoving off-diagonal coupling between coordinate %d and others." % (location+1))
              for j in range(len(H)): # gives first dimension length
                if j != location:
                  H[j][location] = H[location][j] = 0

    return

"""
def massWeightedUMatrixCart(masses): 
    atom = 1 
    masses = [15.9994, 1.00794, 1.00794]
    U = np.zeros((3 * nAtom, 3 * nAtom), float)
    for i in range (0, (3 * nAtom)):
        U[i][i] = 1 / sqrt(masses[atom - 1])
        if (i % 3 == 0):
            nAtom += 1
    return U
"""

def convertHessianToInternals(H, intcos, geom, masses=None, fx=None):
    print_opt("Converting Hessian from cartesians to internals.\n")
    print_opt("This implementation only correct at stationary points.\n")

    #U = massWeightedUMatrixCart(masses)
    #U = np.zeros((3 * nAtom, 3 * nAtom), float)
    #for i in range (3 * nAtom):
    #    U[i][i] = 1

    G = Gmat(intcos, geom, masses)
    #G = Gmat(intcos, geom)
    Ginv = symmMatInv(G)
    print_opt("G inverse\n")
    printMat(Ginv)

    B = Bmat(intcos, geom, masses)
    #B = Bmat(intcos, geom,)
    print_opt("B matrix\n")
    printMat(B)
    Atranspose = np.dot(Ginv, B)
    print_opt("Atranspose\n")
    printMat(Atranspose)

    Hq = np.dot(Atranspose, np.dot(H, Atranspose.T))
    return Hq

def convertHessianToCartesians(Hint, intcos, geom, masses=None, fq=None):
    print_opt("Converting Hessian from internals to cartesians.\n")
    print_opt("This implementation only correct at stationary points.\n") 

    B = Bmat(intcos, geom, masses)
    Hx = np.dot(B.T, np.dot(Hint, B))
    return Hx

