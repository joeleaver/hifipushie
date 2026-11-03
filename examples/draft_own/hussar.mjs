// A hussar jacket body drafted on bent's block (T5 proof): fronts edge to edge for a zip with the hem cut away to a
// point at centre front, back panels with a centre-back seam, a tall stand collar, bent's two-piece sleeve.
import { Design } from '@freesewing/core'
import { back as bentBack, front as bentFront, topsleeve, undersleeve } from '@freesewing/bent'
import { collarStand as simonStand } from '@freesewing/simon'

const HEM = 120 // side hem: this far below the waist (mm): the reference ends at the hip
const CF_END = 40 // the zip's end at centre front, below the waist: the fronts are cut away from here
const TIP = [70, 135] // the cutaway's tip: this far out from CF and below the waist
const COLLAR_H = 48, COLLAR_IN = 10 // the stand: height, and how far its top edge comes in at each end
const HIDE = { from: true, inherited: true }
const hideAll = (paths) => { for (const k of Object.keys(paths)) paths[k].hide() }

const back = {
  name: 'hussar.back', from: bentBack, hide: HIDE,
  draft: ({ points, Point, paths, Path, store, part }) => {
    hideAll(paths)
    points.cbHem2 = new Point(0, points.cbWaist.y + HEM)
    points.hem2 = new Point(points.hem.x, points.cbHem2.y)
    const neck = new Path().move(points.hps).curve_(points.neckCp2, points.cbNeck)
    store.set('backNeck', neck.length())
    paths.seam = new Path().move(points.cbNeck).line(points.cbHem2).line(points.hem2).line(points.armhole)
      .curve(points.armholeCp2, points.armholeHollowCp1, points.armholeHollow)
      .curve(points.armholeHollowCp2, points.armholePitchCp1, points.armholePitch)
      .curve(points.armholePitchCp2, points.shoulderCp1, points.shoulder).line(points.hps).join(neck).close()
    return part
  },
}

const front = {
  name: 'hussar.front', from: bentFront, hide: HIDE,
  draft: ({ points, Point, paths, Path, store, part }) => {
    hideAll(paths)
    points.hem2 = new Point(points.hem.x, points.cfWaist.y + HEM)
    points.cfPoint = new Point(0, points.cfWaist.y + CF_END)
    points.cutTip = new Point(TIP[0], points.cfWaist.y + TIP[1])
    points.cutCp = new Point(TIP[0] * 0.2, points.cutTip.y)
    store.set('frontNeck', paths.frontCollar.length())
    paths.seam = new Path().move(points.cfNeck).line(points.cfPoint)._curve(points.cutCp, points.cutTip).line(points.hem2)
      .line(points.armhole).curve(points.armholeCp2, points.armholeHollowCp1, points.armholeHollow)
      .curve(points.armholeHollowCp2, points.armholePitchCp1, points.armholePitch).join(paths.frontArmhole)
      .line(points.s3CollarSplit).join(paths.frontCollar).close()
    return part
  },
}

// The stand is simon's collarStand (a patternmaker's curved stand: its centre line bends, the edges follow), its neck
// edge sized by the same collarEase as the neckline. A tall jacket stand on a jacket neckline that drops at the front must
// lean in and stay full height at CF: its neck edge's front ends rise (jaeger.collarStand rises ~0.47 x the front drop),
// so simon's bend is set past its shirt range the rising way (options in options.json); no button extension (hooks).
const collar = {
  name: 'hussar.collar', from: simonStand, after: [back, front],
  draft: ({ points, snippets, Snippet, part }) => {
    snippets.hook = new Snippet('button', points.leftCf)
    snippets.eye = new Snippet('buttonhole', points.rightCf)
    return part
  },
}

const top = { name: 'hussar.topsleeve', from: topsleeve, after: [back, front], hide: HIDE,
  draft: ({ part }) => part }
const under = { name: 'hussar.undersleeve', from: undersleeve, after: [back, front], hide: HIDE,
  draft: ({ part }) => part }

export default new Design({ parts: [back, front, collar, top, under] })
