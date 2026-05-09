package service

import (
	"time"

	"cs-kb-api/internal/model"
)

func seedSOPs() []model.SOP {
	updatedFood := time.Date(2026, 5, 1, 10, 0, 0, 0, time.UTC)
	updatedPayment := time.Date(2026, 4, 20, 9, 30, 0, 0, time.UTC)
	updatedSafety := time.Date(2026, 4, 12, 8, 45, 0, 0, time.UTC)

	return []model.SOP{
		{
			ID:               "sop-food-missing-item",
			Code:             "SOP-FOOD-MISSING-ITEM",
			Title:            "Xu ly case khach khong nhan du mon",
			Summary:          "Huong dan xu ly case khach bao thieu mon, sai mon hoac thieu topping trong don beFood.",
			Audience:         []string{"customer"},
			Vertical:         "food",
			Category:         "case_handling",
			Tags:             []string{"missing_item", "refund", "merchant", "food"},
			CaseReasons:      []string{"CR_FOOD_MISSING_ITEM"},
			Status:           "active",
			CurrentVersionID: "ver-food-missing-item-3",
			OwnerTeam:        "CS Ops",
			UpdatedAt:        updatedFood,
			Analytics:        model.SOPMetrics{Views: 1240, MacroCopy: 730, Helpful: 210, NotHelpful: 18},
			CurrentVersion: model.SOPVersion{
				ID:            "ver-food-missing-item-3",
				SOPID:         "sop-food-missing-item",
				VersionNumber: 3,
				Status:        "published",
				EffectiveFrom: updatedFood,
				CreatedBy:     "sop-admin",
				ApprovedBy:    "cs-lead",
				ChangeSummary: "Cap nhat rule refund cho case thieu topping.",
				PublishedAt:   updatedFood,
				Sections: model.SOPSections{
					WhenToApply:      "Ap dung khi khach bao khong nhan du mon, sai mon, thieu topping hoac merchant xac nhan dong goi thieu.",
					InputRequirement: "Kiem tra order ID, anh chup mon nhan duoc, thoi gian bao loi, gia tri item va log merchant neu co.",
					Checklist: []string{
						"Xac minh order va trang thai giao hang.",
						"Doi chieu item khach bao thieu voi order detail.",
						"Kiem tra bang chung tu khach va merchant note.",
						"Ap dung rule refund theo gia tri item bi thieu.",
						"Gui macro ket qua va ghi nhan case reason.",
					},
					AgentScript: "Xac nhan thong tin voi khach, tranh cam ket refund truoc khi du dieu kien.",
					MacroResponses: []model.Macro{
						{
							Title:   "Thong bao dang kiem tra",
							Content: "Em da tiep nhan thong tin don hang cua anh/chi va se kiem tra voi cac ben lien quan truoc khi cap nhat huong xu ly.",
						},
						{
							Title:   "Xac nhan hoan tien item thieu",
							Content: "Don hang cua anh/chi du dieu kien ho tro theo chinh sach hien hanh. He thong se cap nhat khoan hoan tien theo gia tri mon bi thieu.",
						},
					},
					SLA:             "Cap nhat ket qua trong 24h neu can xac minh merchant.",
					Escalation:      "Escalate Lead neu gia tri refund vuot nguong hoac khach co lich su dispute bat thuong.",
					RelatedPolicies: []string{"POLICY-FOOD-REFUND", "SOP-MERCHANT-CONTACT"},
				},
			},
		},
		{
			ID:               "sop-payment-double-charge",
			Code:             "SOP-PAYMENT-DOUBLE-CHARGE",
			Title:            "Xu ly giao dich bi tru tien hai lan",
			Summary:          "Quy trinh xac minh va ho tro khach hang bao bi tru tien lap cho mot chuyen di hoac don hang.",
			Audience:         []string{"customer"},
			Vertical:         "payment",
			Category:         "verification",
			Tags:             []string{"payment", "double_charge", "refund", "bank"},
			CaseReasons:      []string{"CR_PAYMENT_DOUBLE_CHARGE"},
			Status:           "active",
			CurrentVersionID: "ver-payment-double-charge-2",
			OwnerTeam:        "Payment Ops",
			UpdatedAt:        updatedPayment,
			Analytics:        model.SOPMetrics{Views: 820, MacroCopy: 390, Helpful: 130, NotHelpful: 11},
			CurrentVersion: model.SOPVersion{
				ID:            "ver-payment-double-charge-2",
				SOPID:         "sop-payment-double-charge",
				VersionNumber: 2,
				Status:        "published",
				EffectiveFrom: updatedPayment,
				CreatedBy:     "payment-admin",
				ApprovedBy:    "cs-lead",
				ChangeSummary: "Bo sung yeu cau bank statement.",
				PublishedAt:   updatedPayment,
				Sections: model.SOPSections{
					WhenToApply:      "Ap dung khi khach bao mot giao dich bi tru tien hai lan hoac co debit nhung don hang that bai.",
					InputRequirement: "Can order/booking ID, thoi gian giao dich, payment method, screenshot banking va transaction reference.",
					Checklist: []string{
						"Kiem tra payment status tren he thong.",
						"Doi chieu transaction reference voi payment gateway.",
						"Neu giao dich pending, huong dan khach cho bank release.",
						"Neu capture duplicate, tao ticket refund cho Payment Ops.",
					},
					AgentScript: "Giai thich ro khac biet giua pending authorization va captured charge.",
					MacroResponses: []model.Macro{
						{
							Title:   "Can bo sung sao ke",
							Content: "Anh/chi vui long gui them anh chup giao dich tren ung dung ngan hang de ben em doi chieu voi cong thanh toan.",
						},
					},
					SLA:        "Payment Ops phan hoi trong 2 ngay lam viec.",
					Escalation: "Escalate Payment Ops neu co transaction reference bi capture duplicate.",
				},
			},
		},
		{
			ID:               "sop-safety-driver-incident",
			Code:             "SOP-SAFETY-DRIVER-INCIDENT",
			Title:            "Escalation su co an toan lien quan tai xe",
			Summary:          "Huong dan ghi nhan, phan loai va escalate case an toan co lien quan tai xe.",
			Audience:         []string{"customer", "driver"},
			Vertical:         "safety",
			Category:         "escalation",
			Tags:             []string{"safety", "driver", "incident", "escalation"},
			CaseReasons:      []string{"CR_SAFETY_DRIVER_INCIDENT"},
			Status:           "active",
			CurrentVersionID: "ver-safety-driver-incident-1",
			OwnerTeam:        "Trust Safety",
			UpdatedAt:        updatedSafety,
			Analytics:        model.SOPMetrics{Views: 540, MacroCopy: 120, Helpful: 95, NotHelpful: 6},
			CurrentVersion: model.SOPVersion{
				ID:            "ver-safety-driver-incident-1",
				SOPID:         "sop-safety-driver-incident",
				VersionNumber: 1,
				Status:        "published",
				EffectiveFrom: updatedSafety,
				CreatedBy:     "safety-admin",
				ApprovedBy:    "safety-lead",
				ChangeSummary: "Initial controlled SOP.",
				PublishedAt:   updatedSafety,
				Sections: model.SOPSections{
					WhenToApply:      "Ap dung cho case khach hoac tai xe bao su co an toan, de doa, quay roi, tai nan hoac hanh vi bat thuong.",
					InputRequirement: "Can booking ID, thoi gian, dia diem, doi tuong lien quan, mo ta su viec va bang chung neu co.",
					Checklist: []string{
						"Uu tien xac nhan tinh trang an toan hien tai.",
						"Thu thap thong tin toi thieu, khong tranh luan voi nguoi bao cao.",
						"Phan loai muc do nghiem trong theo rubric Trust Safety.",
						"Escalate ngay neu co nguy co tiep dien hoac ton hai than the.",
					},
					AgentScript: "Giu tone trung lap, uu tien an toan, khong dua ra ket luan khi chua co review.",
					MacroResponses: []model.Macro{
						{
							Title:   "Tiep nhan su co an toan",
							Content: "Ben em da ghi nhan thong tin va se chuyen den bo phan phu trach an toan de kiem tra theo quy trinh uu tien.",
						},
					},
					SLA:        "Escalate critical case trong 15 phut.",
					Escalation: "Escalate Trust Safety ngay voi threat, accident, harassment hoac repeat offender.",
				},
			},
		},
	}
}
