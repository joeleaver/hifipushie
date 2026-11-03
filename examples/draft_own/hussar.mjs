// A hussar jacket body drafted on bent's block (T5 proof): fronts edge to edge for a zip with the hem cut away to a
// point at centre front, back panels with a centre-back seam, a tall stand collar, bent's two-piece sleeve.
import { Design } from '@freesewing/core'
import { back as bentBack, front as bentFront, topsleeve, undersleeve } from '@freesewing/bent'
import { collarStand as simonStand } from '@freesewing/simon'

const HEM = 120 // side hem: this far below the waist (mm): the reference ends at the hip
const CF_END = 40 // the zip's end at centre front, below the waist: the fronts are cut away from here
const TIP = [70, 135] // the cutaway's tip: this far out from CF and below the waist
const STEP_OUT = 60 // the cutaway's square step out from CF at the zip's end (mm)
const ROUND = 16 // the stand's front top corners: rounded over this much (mm; the reference's are round)
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
    // the reference's cutaway: the front edge comes down to the zip's end, steps OUT in a square corner, then drops to
    // a point; the hem runs from the point to the side (corners stay corners: traced, not an arc)
    points.cutStep = new Point(STEP_OUT, points.cfPoint.y)
    points.cutTip = new Point(TIP[0], points.cfWaist.y + TIP[1])
    store.set('frontNeck', paths.frontCollar.length())
    paths.seam = new Path().move(points.cfNeck).line(points.cfPoint).line(points.cutStep).line(points.cutTip).line(points.hem2)
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
  draft: ({ points, paths, Path, snippets, Snippet, part }) => {
    // simon's outline redrawn with its front TOP corners rounded (the reference's), everything else simon's own points
    for (const s of ['right', 'left']) {
      const c = points[s + 'TopCf'], b = points[s + 'BottomEdge'], h = points[s + 'TopHinge']
      points[s + 'EndUp'] = c.shiftTowards(b, ROUND)
      points[s + 'TopIn'] = c.shiftTowards(h, ROUND)
      points[s + 'EndUpCp'] = points[s + 'EndUp'].shiftFractionTowards(c, 0.55)
      points[s + 'TopInCp'] = points[s + 'TopIn'].shiftFractionTowards(c, 0.55)
    }
    paths.seam = new Path().move(points.bottomMid)
      .curve(points.bottomMidCp2, points.rightBottomHingeCp1, points.rightBottomHinge)
      .curve(points.rightBottomHingeCp2, points.rightBottomCfCp1, points.rightBottomCf).line(points.rightBottomEdge)
      .line(points.rightEndUp).curve(points.rightEndUpCp, points.rightTopInCp, points.rightTopIn)
      .curve(points.rightTopHingeCp1, points.rightTopHingeCp1, points.rightTopHinge)
      .curve(points.rightTopHingeCp2, points.topMidCp1, points.topMid)
      .curve(points.topMidCp2, points.leftTopHingeCp1, points.leftTopHinge)
      .curve(points.leftTopHingeCp2, points.leftTopHingeCp2, points.leftTopIn)
      .curve(points.leftTopInCp, points.leftEndUpCp, points.leftEndUp).line(points.leftBottomEdge).line(points.leftBottomCf)
      .curve(points.leftBottomCfCp2, points.leftBottomHingeCp1, points.leftBottomHinge)
      .curve(points.leftBottomHingeCp2, points.bottomMidCp1, points.bottomMid).close().attr('class', 'fabric')
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
